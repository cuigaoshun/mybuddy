from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from apscheduler.triggers.cron import CronTrigger

from app.core.config import AppRuntimeConfig
from app.storage.reminder_models import (
    CreatedReminder,
    ReminderCreateCommand,
    ReminderJob,
    ReminderJobStatus,
    ReminderSchedule,
    ReminderScheduleStatus,
)
from app.storage.reminder_repository import ReminderRepository

CLAIM_BATCH_SIZE = 20
LEASE_SECONDS = 60
MAX_ATTEMPTS = 3
BLOCKED_RETRY_WINDOW_MINUTES = 30
MINIMUM_INTERVAL_HOURS = 8


@dataclass(frozen=True, slots=True)
class ReminderValidationError(Exception):
    """提醒参数不合法。"""

    message: str

    def __str__(self) -> str:
        return self.message


class ReminderService:
    """提醒领域服务，负责规则创建、物化与状态推进。"""

    def __init__(self, repository: ReminderRepository, runtime_config: AppRuntimeConfig) -> None:
        self._repository = repository
        self._runtime_config = runtime_config

    def create_reminder(self, command: ReminderCreateCommand) -> CreatedReminder:
        """创建一次性或重复提醒。"""

        normalized_command = _normalize_create_command(command=command)
        now = datetime.now(UTC)
        timezone_name = self._resolve_timezone_name()
        if normalized_command.run_at is not None:
            run_at = self._require_run_at(normalized_command)
            schedule = ReminderSchedule(
                id=None,
                user_id=normalized_command.user_id,
                im_type=normalized_command.im_type,
                chat_id=normalized_command.chat_id,
                third_party_user_id=normalized_command.third_party_user_id,
                chat_type=normalized_command.chat_type,
                reminder_text=normalized_command.reminder_text,
                timezone=timezone_name,
                run_at=run_at,
                cron_expr=None,
                next_run_at=run_at,
                status=ReminderScheduleStatus.ACTIVE,
                source_message_id=normalized_command.source_message_id,
                source_message_time=_normalize_datetime(normalized_command.source_message_time),
                source_text=normalized_command.source_text,
                last_triggered_at=None,
                created_at=now,
                updated_at=now,
            )
            placeholder_job = ReminderJob(
                id=None,
                schedule_id=0,
                scheduled_for=run_at,
                status=ReminderJobStatus.PENDING,
                lease_owner=None,
                lease_until=None,
                attempt_count=0,
                available_at=run_at,
                last_error=None,
                dedupe_key="",
                sent_message_id=None,
                sent_at=None,
                created_at=now,
                updated_at=now,
            )
            return self._repository.create_once_schedule_with_job(schedule, placeholder_job)
        cron_expr = _require_cron_expr(normalized_command)
        self._validate_cron_frequency(cron_expr=cron_expr)
        next_run_at = _compute_next_cron_fire_time(
            cron_expr=cron_expr,
            timezone_name=timezone_name,
            now=now,
        )
        schedule = ReminderSchedule(
            id=None,
            user_id=normalized_command.user_id,
            im_type=normalized_command.im_type,
            chat_id=normalized_command.chat_id,
            third_party_user_id=normalized_command.third_party_user_id,
            chat_type=normalized_command.chat_type,
            reminder_text=normalized_command.reminder_text,
            timezone=timezone_name,
            run_at=None,
            cron_expr=cron_expr,
            next_run_at=next_run_at,
            status=ReminderScheduleStatus.ACTIVE,
            source_message_id=normalized_command.source_message_id,
            source_message_time=_normalize_datetime(normalized_command.source_message_time),
            source_text=normalized_command.source_text,
            last_triggered_at=None,
            created_at=now,
            updated_at=now,
        )
        return CreatedReminder(schedule=self._repository.create_schedule(schedule), first_job=None)

    def materialize_due_recurring_jobs(self, now: datetime) -> tuple[int, ...]:
        """为到期的重复提醒物化执行任务。"""

        return self._repository.materialize_due_recurring_jobs(
            now=_normalize_datetime(now),
            limit=CLAIM_BATCH_SIZE,
        )

    def claim_due_jobs(self, now: datetime) -> tuple[int, ...]:
        """认领当前可执行提醒任务。"""

        normalized_now = _normalize_datetime(now)
        lease_owner = uuid4().hex
        lease_until = normalized_now + timedelta(seconds=LEASE_SECONDS)
        return self._repository.claim_due_jobs(
            now=normalized_now,
            lease_owner=lease_owner,
            lease_until=lease_until,
            limit=CLAIM_BATCH_SIZE,
        )

    def mark_job_retryable(self, job_id: int, attempt_count: int, error_message: str) -> None:
        """把任务标记为可重试失败。"""

        if attempt_count >= MAX_ATTEMPTS:
            self._repository.mark_job_failed(job_id=job_id, last_error=error_message)
            return
        available_at = datetime.now(UTC) + timedelta(minutes=1)
        self._repository.mark_job_retryable(
            job_id=job_id,
            available_at=available_at,
            last_error=error_message,
        )

    def mark_job_blocked_user_route(self, job_id: int, attempt_count: int, error_message: str) -> None:
        """把缺少发送路由的任务标记为阻塞或最终失败。"""

        if attempt_count >= MAX_ATTEMPTS:
            self._repository.mark_job_failed(job_id=job_id, last_error=error_message)
            return
        available_at = datetime.now(UTC) + timedelta(minutes=BLOCKED_RETRY_WINDOW_MINUTES)
        self._repository.mark_job_blocked_user_route(
            job_id=job_id,
            available_at=available_at,
            last_error=error_message,
        )

    def _require_run_at(self, command: ReminderCreateCommand) -> datetime:
        if command.run_at is None:
            raise ReminderValidationError("一次性提醒缺少 run_at")
        run_at = _normalize_scheduled_datetime(command.run_at, self._resolve_timezone_name())
        if run_at <= datetime.now(UTC):
            raise ReminderValidationError("一次性提醒时间必须晚于当前时间")
        return run_at

    def _validate_cron_frequency(self, cron_expr: str) -> None:
        timezone_name = self._resolve_timezone_name()
        first_fire_time = _compute_next_cron_fire_time(cron_expr=cron_expr, timezone_name=timezone_name, now=datetime.now(UTC))
        second_fire_time = _compute_next_cron_fire_time(cron_expr=cron_expr, timezone_name=timezone_name, now=first_fire_time + timedelta(seconds=1))
        if second_fire_time - first_fire_time < timedelta(hours=MINIMUM_INTERVAL_HOURS):
            raise ReminderValidationError(f"重复提醒频率不能高于每 {MINIMUM_INTERVAL_HOURS} 小时一次")

    def _resolve_timezone_name(self) -> str:
        timezone_name = self._runtime_config.timezone
        if timezone_name == "":
            raise ReminderValidationError("全局 timezone 不能为空")
        _resolve_zoneinfo(timezone_name)
        return timezone_name


def _normalize_create_command(command: ReminderCreateCommand) -> ReminderCreateCommand:
    if command.reminder_text.strip() == "":
        raise ReminderValidationError("提醒内容不能为空")
    if (command.run_at is None) == (command.cron_expr is None):
        raise ReminderValidationError("run_at 和 cron_expr 必须且只能传一个")
    return ReminderCreateCommand(
        user_id=command.user_id,
        im_type=command.im_type,
        chat_id=command.chat_id,
        third_party_user_id=command.third_party_user_id,
        chat_type=command.chat_type,
        reminder_text=command.reminder_text.strip(),
        source_message_id=command.source_message_id,
        source_message_time=_normalize_datetime(command.source_message_time),
        source_text=command.source_text.strip(),
        run_at=_normalize_optional_datetime(command.run_at),
        cron_expr=_normalize_optional_cron_expr(command.cron_expr),
    )


def _require_cron_expr(command: ReminderCreateCommand) -> str:
    if command.cron_expr is None or command.cron_expr == "":
        raise ReminderValidationError("重复提醒缺少 cron_expr")
    return command.cron_expr


def _compute_next_cron_fire_time(cron_expr: str, timezone_name: str, now: datetime) -> datetime:
    zone = _resolve_zoneinfo(timezone_name)
    trigger = CronTrigger.from_crontab(cron_expr, timezone=zone)
    next_fire_time = trigger.get_next_fire_time(previous_fire_time=None, now=now.astimezone(zone))
    if next_fire_time is None:
        raise ReminderValidationError("无法计算下一次提醒时间")
    return next_fire_time.astimezone(UTC)


def _resolve_zoneinfo(timezone_name: str) -> ZoneInfo:
    try:
        return ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise ReminderValidationError(f"未知时区: {timezone_name}") from exc


def _normalize_optional_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return _normalize_datetime(value)


def _normalize_optional_cron_expr(value: str | None) -> str | None:
    if value is None:
        return None
    normalized_value = value.strip()
    if normalized_value == "":
        return None
    return normalized_value


def _normalize_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _normalize_scheduled_datetime(value: datetime, timezone_name: str) -> datetime:
    if value.tzinfo is None:
        localized_value = value.replace(tzinfo=_resolve_zoneinfo(timezone_name))
        return localized_value.astimezone(UTC)
    return value.astimezone(UTC)
