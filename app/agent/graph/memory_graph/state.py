from __future__ import annotations

from datetime import UTC, datetime
from typing import TypeAlias

from pydantic import BaseModel, ConfigDict, Field

from app.memory.models import MemoryRecord, PendingMemorySession, UserMemory, UserMemoryProfile

UserProfileScalarPatchValue: TypeAlias = str | bool | int | float | None


class MemoryCandidate(BaseModel):
    """单条候选长期记忆。"""

    model_config = ConfigDict(frozen=True)

    category: str
    content: str
    importance: float = 0.0


class UserMemoryAffinityPatch(BaseModel):
    """用户关系好感度的增量更新。"""

    model_config = ConfigDict(frozen=True)

    level: int | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    notes: str | None = None


class UserMemoryRelationshipPatch(BaseModel):
    """用户关系结构的增量更新。"""

    model_config = ConfigDict(frozen=True)

    affinity: UserMemoryAffinityPatch | None = None


class UserProfilePatch(BaseModel):
    """用户画像的增量更新结构。"""

    model_config = ConfigDict(frozen=True)

    profile: dict[str, UserProfileScalarPatchValue] | None = None
    preferences: dict[str, UserProfileScalarPatchValue] | None = None
    relationship: UserMemoryRelationshipPatch | None = None


class MemoryExtractionResponse(BaseModel):
    """长期记忆候选提取结果。"""

    model_config = ConfigDict(frozen=True)

    candidates: tuple[MemoryCandidate, ...] = ()


class MemoryMergeResponse(BaseModel):
    """长期记忆合并结果。"""

    model_config = ConfigDict(frozen=True)

    long_term_memory_summary: str | None = None
    user_profile_patch: UserProfilePatch = Field(default_factory=UserProfilePatch)


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
