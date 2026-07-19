from __future__ import annotations

from collections.abc import Collection
from datetime import UTC, datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import BigInteger, Column, DateTime, Identity, Index, MetaData, SmallInteger, Table, Text, Uuid, bindparam, desc, func, select
from sqlalchemy.dialects.postgresql import JSONB, insert
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

from app.storage.models import MemoryRecord, RetrievedMemoryHit
from app.storage.repositories import ConversationMemoryRepository

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
            Column("user_id", Uuid(as_uuid=False), nullable=False),
            Column("chat_id", Text, nullable=False),
            Column("message_id", Text, nullable=False),
            Column("type", SmallInteger, nullable=False),
            Column("im_type", Text, nullable=False),
            Column("message_time", DateTime(timezone=True), nullable=False),
            Column("content_type", Text, nullable=False),
            Column("content", JSONB, nullable=False),
            Column("content_vector", Vector(768), nullable=False),
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
        exclude_message_id: str | None = None,
    ) -> list[MemoryRecord]:
        """按用户查询最近 10 条对话记忆。"""
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

    def search_similar_by_user(
        self,
        user_id: str,
        im_type: str,
        chat_id: str,
        query_vector: list[float],
        limit: int,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        exclude_message_ids: Collection[str] | None = None,
    ) -> list[MemoryRecord]:
        """按向量相似度召回指定会话下最接近的历史消息。"""
        distance = self._table.c.content_vector.cosine_distance(query_vector)
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
            .order_by(distance, desc(self._table.c.id))
            .limit(limit)
        )
        statement = _apply_time_range_filters(statement, self._table.c.message_time, start_time, end_time)
        if exclude_message_ids:
            statement = statement.where(self._table.c.message_id.not_in(list(exclude_message_ids)))

        with self._engine.begin() as connection:
            rows = connection.execute(statement).mappings().all()

        return [
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

    def search_similar_hits_by_user(
        self,
        user_id: str,
        query_vector: list[float],
        limit: int,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        exclude_message_ids: Collection[str] | None = None,
    ) -> list[RetrievedMemoryHit]:
        distance = self._table.c.content_vector.cosine_distance(query_vector)
        score = (1 - distance).label("score")
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
                score,
            )
            .where(
                self._table.c.user_id == user_id,
            )
            .order_by(desc(score), desc(self._table.c.id))
            .limit(limit)
        )
        statement = _apply_time_range_filters(statement, self._table.c.message_time, start_time, end_time)
        if exclude_message_ids:
            statement = statement.where(self._table.c.message_id.not_in(list(exclude_message_ids)))

        with self._engine.begin() as connection:
            rows = connection.execute(statement).mappings().all()

        return [
            RetrievedMemoryHit(
                record=MemoryRecord(
                    user_id=row["user_id"],
                    chat_id=row["chat_id"],
                    message_id=row["message_id"],
                    message_type=row["type"],
                    im_type=row["im_type"],
                    message_time=row["message_time"],
                    content_type=row["content_type"],
                    content=row["content"],
                ),
                score=float(row["score"]),
            )
            for row in rows
        ]

    def search_text_by_user(
        self,
        user_id: str,
        im_type: str,
        chat_id: str,
        query_text: str,
        limit: int,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        exclude_message_ids: Collection[str] | None = None,
    ) -> list[MemoryRecord]:
        """按全文检索查询指定会话下的历史消息。"""
        ts_query = func.websearch_to_tsquery("simple", bindparam("search_text", query_text))
        search_vector = func.to_tsvector(
            "simple",
            func.coalesce(self._table.c.content.op("->>")("text"), ""),
        )
        rank = func.ts_rank_cd(search_vector, ts_query)
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
                search_vector.op("@@")(ts_query),
            )
            .order_by(desc(rank), desc(self._table.c.message_time), desc(self._table.c.id))
            .limit(limit)
        )
        statement = _apply_time_range_filters(statement, self._table.c.message_time, start_time, end_time)
        if exclude_message_ids:
            statement = statement.where(self._table.c.message_id.not_in(list(exclude_message_ids)))

        with self._engine.begin() as connection:
            rows = connection.execute(statement).mappings().all()

        return [
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

    def list_by_time_range(
        self,
        user_id: str,
        im_type: str,
        chat_id: str,
        start_time: datetime | None,
        end_time: datetime | None,
        limit: int,
        exclude_message_ids: Collection[str] | None = None,
    ) -> list[MemoryRecord]:
        """按时间范围顺序查询历史消息。"""
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
            .limit(limit)
        )
        statement = _apply_time_range_filters(statement, self._table.c.message_time, start_time, end_time)
        if exclude_message_ids:
            statement = statement.where(self._table.c.message_id.not_in(list(exclude_message_ids)))

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

    def list_message_windows_by_message_ids(
        self,
        user_id: str,
        message_ids: Collection[str],
        exclude_message_ids: Collection[str] | None = None,
    ) -> list[MemoryRecord]:
        """根据命中 message_id 展开每条消息前后各一条时间线消息。"""
        normalized_message_ids = list(dict.fromkeys(message_ids))
        if not normalized_message_ids:
            return []

        timeline = (
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
                func.row_number()
                .over(order_by=(self._table.c.message_time, self._table.c.id))
                .label("timeline_row_number"),
            )
            .where(
                self._table.c.user_id == user_id,
            )
            .subquery()
        )

        matched_rows = (
            select(timeline.c.timeline_row_number)
            .where(timeline.c.message_id.in_(normalized_message_ids))
            .subquery()
        )

        statement = (
            select(
                timeline.c.id,
                timeline.c.user_id,
                timeline.c.chat_id,
                timeline.c.message_id,
                timeline.c.type,
                timeline.c.im_type,
                timeline.c.message_time,
                timeline.c.content_type,
                timeline.c.content,
                timeline.c.timeline_row_number,
            )
            .join(
                matched_rows,
                timeline.c.timeline_row_number.between(
                    matched_rows.c.timeline_row_number - 1,
                    matched_rows.c.timeline_row_number + 1,
                ),
            )
            .distinct()
            .order_by(timeline.c.timeline_row_number)
        )
        if exclude_message_ids:
            statement = statement.where(timeline.c.message_id.not_in(list(exclude_message_ids)))

        with self._engine.begin() as connection:
            rows = connection.execute(statement).mappings().all()

        return [
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

    def list_after_record_id(
        self,
        user_id: str,
        after_record_id: int | None,
        limit: int,
    ) -> list[MemoryRecord]:
        cursor_statement = None
        if after_record_id is not None:
            cursor_statement = (
                select(
                    self._table.c.id.label("cursor_id"),
                )
                .where(
                    self._table.c.user_id == user_id,
                    self._table.c.id == after_record_id,
                )
                .order_by(desc(self._table.c.id))
                .limit(1)
            )

        with self._engine.begin() as connection:
            cursor_row = connection.execute(cursor_statement).mappings().one_or_none() if cursor_statement is not None else None

        statement = (
            select(
                self._table.c.user_id,
                self._table.c.chat_id,
                self._table.c.message_id,
                self._table.c.type,
                self._table.c.im_type,
                self._table.c.message_time,
                self._table.c.content_type,
                self._table.c.content,
                self._table.c.id,
            )
            .where(
                self._table.c.user_id == user_id,
            )
            .order_by(self._table.c.id)
            .limit(limit)
        )
        if cursor_row is not None:
            statement = statement.where(self._table.c.id > cursor_row["cursor_id"])

        with self._engine.begin() as connection:
            rows = connection.execute(statement).mappings().all()

        return [
            MemoryRecord(
                user_id=row["user_id"],
                chat_id=row["chat_id"],
                message_id=row["message_id"],
                message_type=row["type"],
                im_type=row["im_type"],
                message_time=row["message_time"],
                content_type=row["content_type"],
                content=row["content"],
                record_id=row["id"],
            )
            for row in rows
        ]


def _normalize_message_time(message_time: datetime) -> datetime:
    """统一把消息时间转换为 UTC 时区时间。"""
    if message_time.tzinfo is None:
        return message_time.replace(tzinfo=UTC)
    return message_time.astimezone(UTC)


def _apply_time_range_filters(statement, message_time_column, start_time: datetime | None, end_time: datetime | None):
    if start_time is not None:
        statement = statement.where(message_time_column >= _normalize_message_time(start_time))
    if end_time is not None:
        statement = statement.where(message_time_column <= _normalize_message_time(end_time))
    return statement
