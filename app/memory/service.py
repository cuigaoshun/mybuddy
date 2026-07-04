from __future__ import annotations

from typing import Collection

from app.memory.embeddings import EmbeddingProvider
from app.memory.models import MemoryRecord
from app.memory.repositories import ConversationMemoryRepository


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
        embedding = self._embedding_provider.embed_text(_extract_text_content(record))
        return self._repository.save(record, embedding)

    def list_recent_messages(
        self,
        user_id: str,
        im_type: str,
        chat_id: str,
        exclude_message_id: str | None = None,
    ) -> list[MemoryRecord]:
        """读取指定用户在指定平台下最近 10 条对话记忆。"""
        return self._repository.list_recent_by_user(user_id, im_type, chat_id, exclude_message_id)

    def search_similar_messages(
        self,
        user_id: str,
        im_type: str,
        chat_id: str,
        query_text: str,
        limit: int,
        exclude_message_ids: Collection[str] | None = None,
    ) -> list[MemoryRecord]:
        """根据查询文本召回指定会话下最相近的历史消息。"""
        normalized_query = query_text.strip()
        if not normalized_query:
            return []

        embedding = self._embedding_provider.embed_text(normalized_query)
        return self._repository.search_similar_by_user(
            user_id=user_id,
            im_type=im_type,
            chat_id=chat_id,
            query_vector=embedding,
            limit=limit,
            exclude_message_ids=exclude_message_ids,
        )


def _extract_text_content(record: MemoryRecord) -> str:
    """从 JSON 内容中提取一期文本消息的 text 字段。"""
    text_value = record.content.get("text")
    if isinstance(text_value, str):
        return text_value
    return ""
