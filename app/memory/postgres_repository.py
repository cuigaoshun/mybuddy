from __future__ import annotations

from datetime import UTC, datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import BigInteger, Column, DateTime, Identity, Index, MetaData, SmallInteger, Table, Text
from sqlalchemy.dialects.postgresql import JSONB, insert
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

from app.memory.models import MemoryRecord
from app.memory.repositories import ConversationMemoryRepository

CHAT_MEMORY_SCHEMA = "public"


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
            Column("userid", Text, nullable=False),
            Column("chat_id", Text, nullable=False),
            Column("message_id", Text, nullable=False),
            Column("type", SmallInteger, nullable=False),
            Column("im_type", Text, nullable=False),
            Column("message_time", DateTime(timezone=True), nullable=False),
            Column("content_type", Text, nullable=False),
            Column("content", JSONB, nullable=False),
            Column("content_vector", Vector(384), nullable=False),
            Index("idx_chat_memory_userid_message_time", "userid", "message_time"),
            Index("idx_chat_memory_im_type_message_id_type", "im_type", "message_id", "type", unique=True),
            Index(
                "idx_chat_memory_content_vector_hnsw",
                "content_vector",
                postgresql_using="hnsw",
                postgresql_ops={"content_vector": "vector_cosine_ops"},
            ),
        )

    def save(self, record: MemoryRecord, vector: list[float]) -> None:
        """保存一条对话记忆；若命中去重约束则忽略重复写入。"""
        statement = insert(self._table).values(
            userid=record.user_id,
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

        try:
            with self._engine.begin() as connection:
                connection.execute(statement)
        except IntegrityError:
            return


def _normalize_message_time(message_time: datetime) -> datetime:
    """统一把消息时间转换为 UTC 时区时间。"""
    if message_time.tzinfo is None:
        return message_time.replace(tzinfo=UTC)
    return message_time.astimezone(UTC)
