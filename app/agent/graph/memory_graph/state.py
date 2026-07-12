from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict

from app.memory.models import MemoryRecord, PendingMemorySession, UserMemory, UserMemoryProfile


class MemoryCandidate(BaseModel):
    """单条候选长期记忆。"""

    model_config = ConfigDict(frozen=True)

    category: str
    content: str
    importance: float = 0.0


class MemoryGraphState(BaseModel):
    """长期记忆处理图状态。"""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    session: PendingMemorySession
    existing_user_memory: UserMemory | None = None
    conversation_records: tuple[MemoryRecord, ...] = ()
    extracted_candidates: tuple[MemoryCandidate, ...] = ()
    important_candidates: tuple[MemoryCandidate, ...] = ()
    merged_user_memory: UserMemory | None = None
    saved: bool = False


def build_empty_profile() -> UserMemoryProfile:
    return UserMemoryProfile()


def build_now() -> datetime:
    return datetime.now(UTC)
