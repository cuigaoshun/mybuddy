from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import BigInteger, Column, DateTime, Identity, Index, MetaData, Table, Text, Uuid, and_, case, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import Engine

from app.memory.models import ChatSessionInfo, PendingMemorySession
from app.memory.repositories import ChatSessionInfoRepository

CHAT_SESSION_INFO_SCHEMA = "public"
PENDING_MEMORY_PROCESSING_IDLE_MINUTES = 30


class PostgresChatSessionInfoRepository(ChatSessionInfoRepository):
    """基于 SQLAlchemy 的 chat_session_info PostgreSQL 仓储实现。"""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine
        self._metadata = MetaData(schema=CHAT_SESSION_INFO_SCHEMA)
        self._table = Table(
            "chat_session_info",
            self._metadata,
            Column("id", BigInteger, Identity(always=True), primary_key=True),
            Column("user_id", Uuid(as_uuid=False), nullable=False),
            Column("im_type", Text, nullable=False),
            Column("chat_id", Text, nullable=False),
            Column("first_reply_time", DateTime(timezone=True), nullable=True),
            Column("latest_reply_time", DateTime(timezone=True), nullable=True),
            Column("reply_lease_owner", Text, nullable=True),
            Column("reply_lease_until", DateTime(timezone=True), nullable=True),
            Index(
                "uidx_chat_session_info_user_id_im_type_chat_id",
                "user_id",
                "im_type",
                "chat_id",
                unique=True,
            ),
        )

    def get_session_info(self, user_id: str, im_type: str, chat_id: str) -> ChatSessionInfo:
        statement = (
            select(
                self._table.c.user_id,
                self._table.c.im_type,
                self._table.c.chat_id,
                self._table.c.first_reply_time,
                self._table.c.latest_reply_time,
                self._table.c.reply_lease_owner,
                self._table.c.reply_lease_until,
            )
            .where(
                self._table.c.user_id == user_id,
                self._table.c.im_type == im_type,
                self._table.c.chat_id == chat_id,
            )
            .limit(1)
        )

        with self._engine.begin() as connection:
            row = connection.execute(statement).mappings().one_or_none()
        if row is None:
            return ChatSessionInfo(user_id=user_id, im_type=im_type, chat_id=chat_id)
        return ChatSessionInfo(
            user_id=row["user_id"],
            im_type=row["im_type"],
            chat_id=row["chat_id"],
            first_reply_time=row["first_reply_time"],
            latest_reply_time=row["latest_reply_time"],
            lease_owner=row["reply_lease_owner"],
            lease_until=row["reply_lease_until"],
        )

    def try_acquire_reply_lease(
        self,
        user_id: str,
        im_type: str,
        chat_id: str,
        lease_owner: str,
        lease_until: datetime,
    ) -> bool:
        normalized_lease_until = _normalize_time(lease_until)
        now = datetime.now(UTC)
        insert_statement = insert(self._table).values(
            user_id=user_id,
            im_type=im_type,
            chat_id=chat_id,
            reply_lease_owner=lease_owner,
            reply_lease_until=normalized_lease_until,
        )
        insert_statement = insert_statement.on_conflict_do_nothing(
            index_elements=["user_id", "im_type", "chat_id"],
        ).returning(self._table.c.id)

        update_statement = (
            update(self._table)
            .where(
                self._table.c.user_id == user_id,
                self._table.c.im_type == im_type,
                self._table.c.chat_id == chat_id,
                or_(
                    self._table.c.reply_lease_until.is_(None),
                    self._table.c.reply_lease_until < now,
                ),
            )
            .values(
                reply_lease_owner=lease_owner,
                reply_lease_until=normalized_lease_until,
            )
        )

        with self._engine.begin() as connection:
            inserted = connection.execute(insert_statement).scalar_one_or_none()
            if inserted is not None:
                return True
            updated = connection.execute(update_statement)
        return updated.rowcount > 0

    def update_session_info(
        self,
        user_id: str,
        im_type: str,
        chat_id: str,
        first_reply_time: datetime | None = None,
        latest_reply_time: datetime | None = None,
        clear_lease_owner: str | None = None,
    ) -> None:
        normalized_first_reply_time = _normalize_optional_time(first_reply_time)
        normalized_latest_reply_time = _normalize_optional_time(latest_reply_time)

        statement = insert(self._table).values(
            user_id=user_id,
            im_type=im_type,
            chat_id=chat_id,
            first_reply_time=normalized_first_reply_time,
            latest_reply_time=normalized_latest_reply_time,
        )
        statement = statement.on_conflict_do_update(
            index_elements=["user_id", "im_type", "chat_id"],
            set_={
                "first_reply_time": case(
                    (self._table.c.first_reply_time.is_(None), normalized_first_reply_time),
                    else_=self._table.c.first_reply_time,
                )
                if normalized_first_reply_time is not None
                else self._table.c.first_reply_time,
                "latest_reply_time": func.greatest(
                    self._table.c.latest_reply_time,
                    normalized_latest_reply_time,
                )
                if normalized_latest_reply_time is not None
                else self._table.c.latest_reply_time,
                "reply_lease_owner": None if clear_lease_owner is not None else self._table.c.reply_lease_owner,
                "reply_lease_until": None if clear_lease_owner is not None else self._table.c.reply_lease_until,
            },
            where=and_(
                self._table.c.reply_lease_owner == clear_lease_owner,
            )
            if clear_lease_owner is not None
            else None,
        )

        with self._engine.begin() as connection:
            connection.execute(statement)

    def list_sessions_pending_memory_processing(self, limit: int) -> list[PendingMemorySession]:
        pending_before = datetime.now(UTC) - timedelta(minutes=PENDING_MEMORY_PROCESSING_IDLE_MINUTES)
        statement = (
            select(
                self._table.c.user_id,
                self._table.c.im_type,
                self._table.c.chat_id,
                self._table.c.latest_reply_time,
            )
            .where(
                self._table.c.latest_reply_time.is_not(None),
                self._table.c.latest_reply_time <= pending_before,
            )
            .order_by(self._table.c.latest_reply_time, self._table.c.id)
            .limit(limit)
        )

        with self._engine.begin() as connection:
            rows = connection.execute(statement).mappings().all()

        return [
            PendingMemorySession(
                user_id=row["user_id"],
                im_type=row["im_type"],
                chat_id=row["chat_id"],
                latest_reply_time=row["latest_reply_time"],
            )
            for row in rows
            if row["latest_reply_time"] is not None
        ]


def _normalize_optional_time(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return _normalize_time(value)


def _normalize_time(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
