from __future__ import annotations

from datetime import datetime
from typing import Protocol

from app.memory.models import ChatSessionInfo, MemoryRecord


class ConversationMemoryRepository(Protocol):
    def save(self, record: MemoryRecord, vector: list[float]) -> bool:
        ...

    def list_recent_by_user(self, user_id: str, im_type: str, chat_id: str) -> list[MemoryRecord]:
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
