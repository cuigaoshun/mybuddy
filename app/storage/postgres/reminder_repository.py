from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import BigInteger, CheckConstraint, Column, DateTime, Identity, Index, Integer, MetaData, Table, Text, Uuid, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import Engine
from zoneinfo import ZoneInfo

from app.storage.reminder_models import CreatedReminder, ReminderExecutionBundle, ReminderJob, ReminderJobStatus, ReminderSchedule, ReminderScheduleStatus
from app.storage.reminder_repository import ReminderRepository

REMINDER_SCHEMA = "public"


@dataclass(frozen=True, slots=True)
class ReminderTables:
    """reminder 规则表与任务表定义。"""

    metadata: MetaData
    schedule_table: Table
    job_table: Table


class PostgresReminderRepository(ReminderRepository):
    """基于 PostgreSQL 的 reminder 仓储实现。"""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine
        reminder_tables = _build_reminder_tables()
        self._metadata = reminder_tables.metadata
        self._schedule_table = reminder_tables.schedule_table
        self._job_table = reminder_tables.job_table

    def create_schedule(self, schedule: ReminderSchedule) -> ReminderSchedule:
        statement = insert(self._schedule_table).values(**_build_schedule_insert_values(schedule)).returning(*self._schedule_table.c)
        with self._engine.begin() as connection:
            row = connection.execute(statement).mappings().one()
        return _to_schedule(row)

    def create_once_schedule_with_job(self, schedule: ReminderSchedule, job: ReminderJob) -> CreatedReminder:
        with self._engine.begin() as connection:
            schedule_row = connection.execute(
                insert(self._schedule_table)
                .values(**_build_schedule_insert_values(schedule))
                .returning(*self._schedule_table.c)
            ).mappings().one()
            created_schedule = _to_schedule(schedule_row)
            if created_schedule.id is None:
                raise RuntimeError("提醒规则创建失败，缺少主键")
            created_job_values = _build_job_insert_values(job)
            created_job_values.pop("schedule_id", None)
            created_job_values.pop("dedupe_key", None)
            created_job_row = connection.execute(
                insert(self._job_table)
                .values(
                    **created_job_values,
                    schedule_id=created_schedule.id,
                    dedupe_key=f"schedule:{created_schedule.id}:at:{job.scheduled_for.isoformat()}",
                )
                .returning(*self._job_table.c)
            ).mappings().one()
        return CreatedReminder(schedule=created_schedule, first_job=_to_job(created_job_row))

    def create_job(self, job: ReminderJob) -> ReminderJob:
        statement = insert(self._job_table).values(**_build_job_insert_values(job)).returning(*self._job_table.c)
        with self._engine.begin() as connection:
            row = connection.execute(statement).mappings().one()
        return _to_job(row)

    def materialize_due_recurring_jobs(self, now: datetime, limit: int) -> tuple[int, ...]:
        normalized_now = _normalize_datetime(now)
        created_job_ids: list[int] = []
        schedule_statement = (
            select(*self._schedule_table.c)
            .where(
                self._schedule_table.c.status == ReminderScheduleStatus.ACTIVE.value,
                self._schedule_table.c.cron_expr.is_not(None),
                self._schedule_table.c.next_run_at.is_not(None),
                self._schedule_table.c.next_run_at <= normalized_now,
            )
            .order_by(self._schedule_table.c.next_run_at, self._schedule_table.c.id)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        with self._engine.begin() as connection:
            schedules = connection.execute(schedule_statement).mappings().all()
            for row in schedules:
                schedule = _to_schedule(row)
                scheduled_for = row["next_run_at"]
                if scheduled_for is None or schedule.id is None:
                    continue
                dedupe_key = f"schedule:{schedule.id}:at:{scheduled_for.isoformat()}"
                job_statement = insert(self._job_table).values(
                    schedule_id=schedule.id,
                    scheduled_for=scheduled_for,
                    status=ReminderJobStatus.PENDING.value,
                    lease_owner=None,
                    lease_until=None,
                    attempt_count=0,
                    available_at=scheduled_for,
                    last_error=None,
                    dedupe_key=dedupe_key,
                    sent_message_id=None,
                    sent_at=None,
                    created_at=normalized_now,
                    updated_at=normalized_now,
                ).on_conflict_do_nothing(index_elements=["dedupe_key"]).returning(self._job_table.c.id)
                created_job_id = connection.execute(job_statement).scalar_one_or_none()
                if created_job_id is not None:
                    created_job_ids.append(created_job_id)
                next_run_at = _compute_next_run_at(schedule=schedule, previous_run_at=scheduled_for)
                connection.execute(
                    update(self._schedule_table)
                    .where(self._schedule_table.c.id == schedule.id)
                    .values(
                        next_run_at=next_run_at,
                        last_triggered_at=scheduled_for,
                        updated_at=normalized_now,
                    )
                )
        return tuple(created_job_ids)

    def claim_due_jobs(self, now: datetime, lease_owner: str, lease_until: datetime, limit: int) -> tuple[int, ...]:
        normalized_now = _normalize_datetime(now)
        normalized_lease_until = _normalize_datetime(lease_until)
        job_statement = (
            select(self._job_table.c.id)
            .where(
                self._job_table.c.status.in_(
                    (
                        ReminderJobStatus.PENDING.value,
                        ReminderJobStatus.RETRYABLE_FAILED.value,
                        ReminderJobStatus.BLOCKED_USER_ROUTE.value,
                    )
                ),
                self._job_table.c.available_at <= normalized_now,
                or_(
                    self._job_table.c.lease_until.is_(None),
                    self._job_table.c.lease_until < normalized_now,
                ),
            )
            .order_by(self._job_table.c.available_at, self._job_table.c.id)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        claimed_job_ids: list[int] = []
        with self._engine.begin() as connection:
            rows = connection.execute(job_statement).all()
            for row in rows:
                job_id = int(row[0])
                updated = connection.execute(
                    update(self._job_table)
                    .where(self._job_table.c.id == job_id)
                    .values(
                        status=ReminderJobStatus.RUNNING.value,
                        lease_owner=lease_owner,
                        lease_until=normalized_lease_until,
                        attempt_count=self._job_table.c.attempt_count + 1,
                        updated_at=normalized_now,
                    )
                )
                if updated.rowcount > 0:
                    claimed_job_ids.append(job_id)
        return tuple(claimed_job_ids)

    def get_execution_bundle(self, job_id: int) -> ReminderExecutionBundle | None:
        statement = _build_execution_bundle_statement(self._job_table, self._schedule_table, job_id)
        with self._engine.begin() as connection:
            row = connection.execute(statement).mappings().one_or_none()
        if row is None:
            return None
        return ReminderExecutionBundle(schedule=_to_schedule(row), job=_to_job(row))

    def mark_job_sent(self, job_id: int, sent_message_id: str, sent_at: datetime) -> None:
        normalized_sent_at = _normalize_datetime(sent_at)
        with self._engine.begin() as connection:
            connection.execute(
                update(self._job_table)
                .where(self._job_table.c.id == job_id)
                .values(
                    status=ReminderJobStatus.SENT.value,
                    sent_message_id=sent_message_id,
                    sent_at=normalized_sent_at,
                    lease_owner=None,
                    lease_until=None,
                    updated_at=normalized_sent_at,
                )
            )

    def mark_job_retryable(self, job_id: int, available_at: datetime, last_error: str) -> None:
        self._mark_job_rescheduled(
            job_id=job_id,
            status=ReminderJobStatus.RETRYABLE_FAILED,
            available_at=available_at,
            last_error=last_error,
        )

    def mark_job_blocked_user_route(self, job_id: int, available_at: datetime, last_error: str) -> None:
        self._mark_job_rescheduled(
            job_id=job_id,
            status=ReminderJobStatus.BLOCKED_USER_ROUTE,
            available_at=available_at,
            last_error=last_error,
        )

    def mark_job_failed(self, job_id: int, last_error: str) -> None:
        normalized_now = datetime.now(UTC)
        with self._engine.begin() as connection:
            connection.execute(
                update(self._job_table)
                .where(self._job_table.c.id == job_id)
                .values(
                    status=ReminderJobStatus.FAILED.value,
                    last_error=last_error,
                    lease_owner=None,
                    lease_until=None,
                    updated_at=normalized_now,
                )
            )

    def _mark_job_rescheduled(self, job_id: int, status: ReminderJobStatus, available_at: datetime, last_error: str) -> None:
        normalized_available_at = _normalize_datetime(available_at)
        with self._engine.begin() as connection:
            connection.execute(
                update(self._job_table)
                .where(self._job_table.c.id == job_id)
                .values(
                    status=status.value,
                    available_at=normalized_available_at,
                    last_error=last_error,
                    lease_owner=None,
                    lease_until=None,
                    updated_at=normalized_available_at,
                )
            )


def _build_reminder_tables() -> ReminderTables:
    metadata = MetaData(schema=REMINDER_SCHEMA)
    schedule_table = Table(
        "reminder_schedule",
        metadata,
        Column("id", BigInteger, Identity(always=True), primary_key=True),
        Column("user_id", Uuid(as_uuid=False), nullable=False),
        Column("im_type", Text, nullable=False),
        Column("chat_id", Text, nullable=False),
        Column("third_party_user_id", Text, nullable=False),
        Column("chat_type", Text, nullable=False),
        Column("reminder_text", Text, nullable=False),
        Column("timezone", Text, nullable=False),
        Column("run_at", DateTime(timezone=True), nullable=True),
        Column("cron_expr", Text, nullable=True),
        Column("next_run_at", DateTime(timezone=True), nullable=True),
        Column("status", Text, nullable=False),
        Column("source_message_id", Text, nullable=False),
        Column("source_message_time", DateTime(timezone=True), nullable=False),
        Column("source_text", Text, nullable=False),
        Column("last_triggered_at", DateTime(timezone=True), nullable=True),
        Column("created_at", DateTime(timezone=True), nullable=False),
        Column("updated_at", DateTime(timezone=True), nullable=False),
        CheckConstraint(
            "(run_at IS NOT NULL AND cron_expr IS NULL) OR (run_at IS NULL AND cron_expr IS NOT NULL)",
            name="chk_reminder_schedule_run_at_xor_cron_expr",
        ),
        Index("idx_reminder_schedule_user_id", "user_id"),
        Index("idx_reminder_schedule_next_run_at", "next_run_at"),
    )
    job_table = Table(
        "reminder_job",
        metadata,
        Column("id", BigInteger, Identity(always=True), primary_key=True),
        Column("schedule_id", BigInteger, nullable=False),
        Column("scheduled_for", DateTime(timezone=True), nullable=False),
        Column("status", Text, nullable=False),
        Column("lease_owner", Text, nullable=True),
        Column("lease_until", DateTime(timezone=True), nullable=True),
        Column("attempt_count", Integer, nullable=False),
        Column("available_at", DateTime(timezone=True), nullable=False),
        Column("last_error", Text, nullable=True),
        Column("dedupe_key", Text, nullable=False),
        Column("sent_message_id", Text, nullable=True),
        Column("sent_at", DateTime(timezone=True), nullable=True),
        Column("created_at", DateTime(timezone=True), nullable=False),
        Column("updated_at", DateTime(timezone=True), nullable=False),
        Index("uidx_reminder_job_dedupe_key", "dedupe_key", unique=True),
        Index("idx_reminder_job_due_status", "status", "available_at"),
        Index("idx_reminder_job_schedule_id", "schedule_id"),
    )
    return ReminderTables(metadata=metadata, schedule_table=schedule_table, job_table=job_table)


def _compute_next_run_at(schedule: ReminderSchedule, previous_run_at: datetime) -> datetime:
    if schedule.cron_expr is None:
        return previous_run_at
    zone = ZoneInfo(schedule.timezone)
    trigger = CronTrigger.from_crontab(schedule.cron_expr, timezone=zone)
    next_run_at = trigger.get_next_fire_time(previous_fire_time=previous_run_at.astimezone(zone), now=previous_run_at.astimezone(zone) + timedelta(seconds=1))
    if next_run_at is None:
        raise RuntimeError("重复提醒无法计算下一次执行时间")
    return next_run_at.astimezone(UTC)


def _build_schedule_insert_values(schedule: ReminderSchedule) -> dict[str, object]:
    return {
        "user_id": schedule.user_id,
        "im_type": schedule.im_type,
        "chat_id": schedule.chat_id,
        "third_party_user_id": schedule.third_party_user_id,
        "chat_type": schedule.chat_type,
        "reminder_text": schedule.reminder_text,
        "timezone": schedule.timezone,
        "run_at": _normalize_optional_datetime(schedule.run_at),
        "cron_expr": schedule.cron_expr,
        "next_run_at": _normalize_optional_datetime(schedule.next_run_at),
        "status": schedule.status.value,
        "source_message_id": schedule.source_message_id,
        "source_message_time": _normalize_datetime(schedule.source_message_time),
        "source_text": schedule.source_text,
        "last_triggered_at": _normalize_optional_datetime(schedule.last_triggered_at),
        "created_at": _normalize_datetime(schedule.created_at),
        "updated_at": _normalize_datetime(schedule.updated_at),
    }


def _build_job_insert_values(job: ReminderJob) -> dict[str, object]:
    return {
        "schedule_id": job.schedule_id,
        "scheduled_for": _normalize_datetime(job.scheduled_for),
        "status": job.status.value,
        "lease_owner": job.lease_owner,
        "lease_until": _normalize_optional_datetime(job.lease_until),
        "attempt_count": job.attempt_count,
        "available_at": _normalize_datetime(job.available_at),
        "last_error": job.last_error,
        "dedupe_key": job.dedupe_key,
        "sent_message_id": job.sent_message_id,
        "sent_at": _normalize_optional_datetime(job.sent_at),
        "created_at": _normalize_datetime(job.created_at),
        "updated_at": _normalize_datetime(job.updated_at),
    }


def _build_execution_bundle_statement(job_table, schedule_table, job_id: int):
    return (
        select(
            job_table.c.id.label("job_id"),
            job_table.c.schedule_id,
            job_table.c.scheduled_for,
            job_table.c.status.label("job_status"),
            job_table.c.lease_owner,
            job_table.c.lease_until,
            job_table.c.attempt_count,
            job_table.c.available_at,
            job_table.c.last_error,
            job_table.c.dedupe_key,
            job_table.c.sent_message_id,
            job_table.c.sent_at,
            job_table.c.created_at.label("job_created_at"),
            job_table.c.updated_at.label("job_updated_at"),
            schedule_table.c.id.label("schedule_id_value"),
            schedule_table.c.user_id,
            schedule_table.c.im_type,
            schedule_table.c.chat_id,
            schedule_table.c.third_party_user_id,
            schedule_table.c.chat_type,
            schedule_table.c.reminder_text,
            schedule_table.c.timezone,
            schedule_table.c.run_at,
            schedule_table.c.cron_expr,
            schedule_table.c.next_run_at,
            schedule_table.c.status.label("schedule_status"),
            schedule_table.c.source_message_id,
            schedule_table.c.source_message_time,
            schedule_table.c.source_text,
            schedule_table.c.last_triggered_at,
            schedule_table.c.created_at.label("schedule_created_at"),
            schedule_table.c.updated_at.label("schedule_updated_at"),
        )
        .select_from(job_table.join(schedule_table, job_table.c.schedule_id == schedule_table.c.id))
        .where(job_table.c.id == job_id)
        .limit(1)
    )


def _to_schedule(row) -> ReminderSchedule:
    return ReminderSchedule(
        id=row.get("schedule_id_value", row.get("id")),
        user_id=row["user_id"],
        im_type=row["im_type"],
        chat_id=row["chat_id"],
        third_party_user_id=row["third_party_user_id"],
        chat_type=row["chat_type"],
        reminder_text=row["reminder_text"],
        timezone=row["timezone"],
        run_at=row["run_at"],
        cron_expr=row["cron_expr"],
        next_run_at=row["next_run_at"],
        status=ReminderScheduleStatus(row.get("schedule_status", row.get("status"))),
        source_message_id=row["source_message_id"],
        source_message_time=row["source_message_time"],
        source_text=row["source_text"],
        last_triggered_at=row["last_triggered_at"],
        created_at=row.get("schedule_created_at", row.get("created_at")),
        updated_at=row.get("schedule_updated_at", row.get("updated_at")),
    )


def _to_job(row) -> ReminderJob:
    return ReminderJob(
        id=row.get("job_id", row.get("id")),
        schedule_id=row["schedule_id"],
        scheduled_for=row["scheduled_for"],
        status=ReminderJobStatus(row.get("job_status", row.get("status"))),
        lease_owner=row["lease_owner"],
        lease_until=row["lease_until"],
        attempt_count=row["attempt_count"],
        available_at=row["available_at"],
        last_error=row["last_error"],
        dedupe_key=row["dedupe_key"],
        sent_message_id=row["sent_message_id"],
        sent_at=row["sent_at"],
        created_at=row.get("job_created_at", row.get("created_at")),
        updated_at=row.get("job_updated_at", row.get("updated_at")),
    )


def _normalize_optional_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return _normalize_datetime(value)


def _normalize_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
