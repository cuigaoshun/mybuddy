from __future__ import annotations

from datetime import UTC, datetime
from typing import Collection

from app.storage.embeddings import EmbeddingProvider
from app.storage.models import ConversationHistoryQuery, HistorySearchResult, MemoryRecord, RetrievedMemoryHit
from app.storage.repositories import ConversationMemoryRepository


class ConversationMemoryService:
    """对话记忆写入服务，负责提取文本并生成向量。"""

    def __init__(
        self,
        embedding_provider: EmbeddingProvider,
        repository: ConversationMemoryRepository,
    ) -> None:
        """注入向量生成器与记忆仓储。"""
        self._embedding_provider = embedding_provider
        self._repository = repository

    def store(self, record: MemoryRecord) -> bool:
        """把一条记忆记录转换为向量后写入仓储。"""
        embedding = self._embedding_provider.embed_document(_extract_text_content(record))
        return self._repository.save(record, embedding)

    def list_recent_messages(
        self,
        user_id: str,
        exclude_message_id: str | None = None,
    ) -> list[MemoryRecord]:
        """读取指定用户最近 10 条对话记忆。"""
        return self._repository.list_recent_by_user(user_id, exclude_message_id=exclude_message_id)

    def search_similar_messages(
        self,
        user_id: str,
        query_text: str,
        limit: int,
        exclude_message_ids: Collection[str] | None = None,
    ) -> list[MemoryRecord]:
        matched_records = self.retrieve_memory_hits(
            user_id=user_id,
            query_text=query_text,
            limit=limit,
            exclude_message_ids=exclude_message_ids,
        )
        if not matched_records:
            return []

        return self.expand_memory_hits(
            user_id=user_id,
            hits=matched_records,
            exclude_message_ids=exclude_message_ids,
        )

    def retrieve_memory_hits(
        self,
        user_id: str,
        query_text: str,
        limit: int,
        exclude_message_ids: Collection[str] | None = None,
    ) -> list[RetrievedMemoryHit]:
        recent_question = query_text.strip()
        if not recent_question:
            return []

        embedding = self._embedding_provider.embed_query(recent_question)
        return self._repository.search_similar_hits_by_user(
            user_id=user_id,
            query_vector=embedding,
            limit=limit,
            exclude_message_ids=exclude_message_ids,
        )

    def expand_memory_hits(
        self,
        user_id: str,
        hits: Collection[RetrievedMemoryHit],
        exclude_message_ids: Collection[str] | None = None,
    ) -> list[MemoryRecord]:
        matched_message_ids = [hit.record.message_id for hit in hits]
        return self._repository.list_message_windows_by_message_ids(
            user_id=user_id,
            message_ids=matched_message_ids,
            exclude_message_ids=exclude_message_ids,
        )

    def list_messages_after_message_id(
        self,
        user_id: str,
        im_type: str,
        chat_id: str,
        after_message_id: str | None,
        limit: int,
    ) -> list[MemoryRecord]:
        return self._repository.list_after_message_id(
            user_id=user_id,
            im_type=im_type,
            chat_id=chat_id,
            after_message_id=after_message_id,
            limit=limit,
        )

    def search_history(self, query: ConversationHistoryQuery) -> list[HistorySearchResult]:
        """按文本与时间范围查询历史消息，支持词法与向量联合召回。"""
        normalized_query = _normalize_history_query(query)
        exclude_message_ids: tuple[str, ...] = ()
        if not normalized_query.text:
            return [
                HistorySearchResult(record=record, matched_by_text=False, matched_by_vector=False)
                for record in self._repository.list_by_time_range(
                    user_id=normalized_query.user_id,
                    im_type=normalized_query.im_type,
                    chat_id=normalized_query.chat_id,
                    start_time=normalized_query.start_time,
                    end_time=normalized_query.end_time,
                    limit=normalized_query.limit,
                    exclude_message_ids=exclude_message_ids,
                )
            ]

        text_records = self._repository.search_text_by_user(
            user_id=normalized_query.user_id,
            im_type=normalized_query.im_type,
            chat_id=normalized_query.chat_id,
            query_text=normalized_query.text,
            limit=normalized_query.limit,
            start_time=normalized_query.start_time,
            end_time=normalized_query.end_time,
            exclude_message_ids=exclude_message_ids,
        )

        query_vector = self._embedding_provider.embed_query(normalized_query.text)
        vector_records = self._repository.search_similar_by_user(
            user_id=normalized_query.user_id,
            im_type=normalized_query.im_type,
            chat_id=normalized_query.chat_id,
            query_vector=query_vector,
            limit=normalized_query.limit,
            start_time=normalized_query.start_time,
            end_time=normalized_query.end_time,
            exclude_message_ids=exclude_message_ids,
        )
        return _merge_history_search_results(
            text_records=text_records,
            vector_records=vector_records,
            limit=normalized_query.limit,
        )


def _extract_text_content(record: MemoryRecord) -> str:
    """从 JSON 内容中提取一期文本消息的 text 字段。"""
    text_value = record.content.get("text")
    if isinstance(text_value, str):
        return text_value
    return ""


def _normalize_history_query(query: ConversationHistoryQuery) -> ConversationHistoryQuery:
    text = query.text.strip()
    start_time = _normalize_optional_datetime(query.start_time)
    end_time = _normalize_optional_datetime(query.end_time)
    if start_time is not None and end_time is not None and start_time > end_time:
        start_time, end_time = end_time, start_time
    limit = max(1, min(query.limit, 10))
    return ConversationHistoryQuery(
        user_id=query.user_id,
        im_type=query.im_type,
        chat_id=query.chat_id,
        text=text,
        start_time=start_time,
        end_time=end_time,
        limit=limit,
    )


def _normalize_optional_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _merge_history_search_results(
    text_records: list[MemoryRecord],
    vector_records: list[MemoryRecord],
    limit: int,
) -> list[HistorySearchResult]:
    rank_scores: dict[str, float] = {}
    matched_by_text: dict[str, bool] = {}
    matched_by_vector: dict[str, bool] = {}
    records_by_message_id: dict[str, MemoryRecord] = {}

    for index, record in enumerate(text_records, start=1):
        records_by_message_id[record.message_id] = record
        matched_by_text[record.message_id] = True
        matched_by_vector.setdefault(record.message_id, False)
        rank_scores[record.message_id] = rank_scores.get(record.message_id, 0.0) + _rrf_score(index)

    for index, record in enumerate(vector_records, start=1):
        records_by_message_id[record.message_id] = record
        matched_by_vector[record.message_id] = True
        matched_by_text.setdefault(record.message_id, False)
        rank_scores[record.message_id] = rank_scores.get(record.message_id, 0.0) + _rrf_score(index)

    sorted_records = sorted(
        records_by_message_id.values(),
        key=lambda record: (
            -rank_scores.get(record.message_id, 0.0),
            -record.message_time.timestamp(),
            record.message_id,
        ),
    )
    return [
        HistorySearchResult(
            record=record,
            matched_by_text=matched_by_text.get(record.message_id, False),
            matched_by_vector=matched_by_vector.get(record.message_id, False),
        )
        for record in sorted_records[:limit]
    ]


def _rrf_score(rank: int) -> float:
    return 1.0 / (60 + rank)
