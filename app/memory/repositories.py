from __future__ import annotations

from typing import Protocol

from app.memory.models import MemoryRecord


class ConversationMemoryRepository(Protocol):
    def save(self, record: MemoryRecord, vector: list[float]) -> None:
        ...

    def list_recent_by_user(self, user_id: str, im_type: str) -> list[MemoryRecord]:
        ...
