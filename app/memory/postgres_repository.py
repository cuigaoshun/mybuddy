from __future__ import annotations

from datetime import UTC, datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import BigInteger, Column, DateTime, Identity, Index, MetaData, SmallInteger, Table, Text, desc, select
from sqlalchemy.dialects.postgresql import JSONB, insert
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

from app.memory.models import MemoryRecord
from app.memory.repositories import ConversationMemoryRepository

CHAT_MEMORY_SCHEMA = "public"
RECENT_MESSAGE_LIMIT = 10


class PostgresConversationMemoryRepository(ConversationMemoryRepository):
    """基于 SQLAlchemy 的 chat_memory PostgreSQL 仓储实现。"""

    def __init__(self, engine: Engine) -> None:
        """初始化 chat_memory 表映射与数据库连接。"""
        self._engine = engine
        self._metadata = MetaData(schema=CHAT_MEMORY_SCHEMA)
        self._table = Table(
            "chat_memory",
            self._metadata,
            Column("id", BigInteger, Identity(always=True), primary_key=True),
            Column("user_id", Text, nullable=False),
            Column("chat_id", Text, nullable=False),
            Column("message_id", Text, nullable=False),
            Column("type", SmallInteger, nullable=False),
            Column("im_type", Text, nullable=False),
            Column("message_time", DateTime(timezone=True), nullable=False),
            Column("content_type", Text, nullable=False),
            Column("content", JSONB, nullable=False),
            Column("content_vector", Vector(384), nullable=False),
            Index("idx_chat_memory_user_id_im_type_message_time", "user_id", "im_type", "message_time"),
            Index("idx_chat_memory_im_type_message_id_type", "im_type", "message_id", "type", unique=True),
            Index(
                "idx_chat_memory_content_vector_hnsw",
                "content_vector",
                postgresql_using="hnsw",
                postgresql_ops={"content_vector": "vector_cosine_ops"},
            ),
        )

    def save(self, record: MemoryRecord, vector: list[float]) -> bool:
        """保存一条对话记忆；若命中去重约束则忽略重复写入。"""
        statement = insert(self._table).values(
            user_id=record.user_id,
            chat_id=record.chat_id,
            message_id=record.message_id,
            type=record.message_type,
            im_type=record.im_type,
            message_time=_normalize_message_time(record.message_time),
            content_type=record.content_type,
            content=record.content,
            content_vector=vector,
        )
        statement = statement.on_conflict_do_nothing(
            index_elements=["im_type", "message_id", "type"],
        )
        statement = statement.returning(self._table.c.id)

        try:
            with self._engine.begin() as connection:
                result = connection.execute(statement)
        except IntegrityError:
            return False
        return result.scalar_one_or_none() is not None

    def list_recent_by_user(
        self,
        user_id: str,
        im_type: str,
        chat_id: str,
        exclude_message_id: str | None = None,
    ) -> list[MemoryRecord]:
        """按用户、平台与会话查询最近 10 条会话记忆。"""
        statement = (
            select(
                self._table.c.id,
                self._table.c.user_id,
                self._table.c.chat_id,
                self._table.c.message_id,
                self._table.c.type,
                self._table.c.im_type,
                self._table.c.message_time,
                self._table.c.content_type,
                self._table.c.content,
            )
            .where(
                self._table.c.user_id == user_id,
                self._table.c.im_type == im_type,
                self._table.c.chat_id == chat_id,
            )
            .order_by(desc(self._table.c.message_time), desc(self._table.c.id))
            .limit(RECENT_MESSAGE_LIMIT)
        )
        if exclude_message_id is not None:
            statement = statement.where(self._table.c.message_id != exclude_message_id)

        with self._engine.begin() as connection:
            rows = connection.execute(statement).mappings().all()

        records = [
            MemoryRecord(
                user_id=row["user_id"],
                chat_id=row["chat_id"],
                message_id=row["message_id"],
                message_type=row["type"],
                im_type=row["im_type"],
                message_time=row["message_time"],
                content_type=row["content_type"],
                content=row["content"],
            )
            for row in rows
        ]
        records.reverse()
        return records


def _normalize_message_time(message_time: datetime) -> datetime:
    """统一把消息时间转换为 UTC 时区时间。"""
    if message_time.tzinfo is None:
        return message_time.replace(tzinfo=UTC)
    return message_time.astimezone(UTC)
