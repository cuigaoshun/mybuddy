from __future__ import annotations

from datetime import datetime
from typing import Collection, Protocol

from app.memory.models import ChatSessionInfo, MemoryRecord, PendingMemorySession, RetrievedMemoryHit, UserMemory


class ConversationMemoryRepository(Protocol):
    def save(self, record: MemoryRecord, vector: list[float]) -> bool:
        ...

    def list_recent_by_user(
        self,
        user_id: str,
        im_type: str,
        chat_id: str,
        exclude_message_id: str | None = None,
    ) -> list[MemoryRecord]:
        ...

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
        ...

    def search_similar_hits_by_user(
        self,
        user_id: str,
        im_type: str,
        chat_id: str,
        query_vector: list[float],
        limit: int,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        exclude_message_ids: Collection[str] | None = None,
    ) -> list[RetrievedMemoryHit]:
        ...

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
        ...

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
        ...

    def list_message_windows_by_message_ids(
        self,
        user_id: str,
        im_type: str,
        chat_id: str,
        message_ids: Collection[str],
        exclude_message_ids: Collection[str] | None = None,
    ) -> list[MemoryRecord]:
        ...

    def list_after_message_id(
        self,
        user_id: str,
        im_type: str,
        chat_id: str,
        after_message_id: str | None,
        limit: int,
    ) -> list[MemoryRecord]:
        ...


class ChatSessionInfoRepository(Protocol):
    def get_session_info(self, user_id: str, im_type: str, chat_id: str) -> ChatSessionInfo:
        ...

    def try_acquire_reply_lease(
        self,
        user_id: str,
        im_type: str,
        chat_id: str,
        lease_owner: str,
        lease_until: datetime,
    ) -> bool:
        ...

    def update_session_info(
        self,
        user_id: str,
        im_type: str,
        chat_id: str,
        first_reply_time: datetime | None = None,
        latest_reply_time: datetime | None = None,
        clear_lease_owner: str | None = None,
    ) -> None:
        ...

    def list_sessions_pending_memory_processing(self, limit: int) -> list[PendingMemorySession]:
        ...


class UserMemoryRepository(Protocol):
    def get_by_user(self, user_id: str, im_type: str) -> UserMemory | None:
        ...

    def save(self, user_memory: UserMemory) -> None:
        ...
