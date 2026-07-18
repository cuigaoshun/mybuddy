from __future__ import annotations

"""长期记忆处理图的状态与结构化模型定义。

这个文件承担两类职责：
1. 定义 LangGraph 在各节点之间流转的状态模型。
2. 定义结构化输出需要复用的候选记忆、画像 patch 和模型返回结果 schema。
"""

from datetime import UTC, datetime
from typing import TypeAlias

from pydantic import BaseModel, ConfigDict, Field

from app.storage.models import MemoryRecord, PendingMemorySession, UserMemory, UserMemoryProfile

UserProfileScalarPatchValue: TypeAlias = str | bool | int | float | None


class MemoryCandidate(BaseModel):
    """单条候选长期记忆。

    这是 extract 节点和 score 节点之间流转的最小记忆单元。
    """

    model_config = ConfigDict(frozen=True)

    category: str
    content: str
    importance: float = 0.0


class UserMemoryAffinityPatch(BaseModel):
    """用户关系好感度的增量更新。

    这里不要求模型返回完整关系对象，只允许返回需要更新的字段。
    """

    model_config = ConfigDict(frozen=True)

    level: int | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    notes: str | None = None


class UserMemoryRelationshipPatch(BaseModel):
    """用户关系结构的增量更新。"""

    model_config = ConfigDict(frozen=True)

    affinity: UserMemoryAffinityPatch | None = None


class UserProfilePatch(BaseModel):
    """用户画像的增量更新结构。

    模型只返回需要新增、修改或清空的字段，
    最终完整画像由本地合并逻辑恢复。
    """

    model_config = ConfigDict(frozen=True)

    profile: dict[str, UserProfileScalarPatchValue] | None = None
    preferences: dict[str, UserProfileScalarPatchValue] | None = None
    relationship: UserMemoryRelationshipPatch | None = None


class MemoryExtractionResponse(BaseModel):
    """长期记忆候选提取结果。

    对应 extract 节点的结构化输出 schema。
    """

    model_config = ConfigDict(frozen=True)

    candidates: tuple[MemoryCandidate, ...] = ()


class MemoryMergeResponse(BaseModel):
    """长期记忆合并结果。

    对应 merge 节点的结构化输出 schema。
    """

    model_config = ConfigDict(frozen=True)

    long_term_memory_summary: str | None = None
    user_profile_patch: UserProfilePatch = Field(default_factory=UserProfilePatch)


class MemoryGraphState(BaseModel):
    """长期记忆处理图状态。

    这里保存长期记忆图在一次处理过程中的全部中间结果，
    保证每个节点都只关心自己需要读写的那一部分状态。
    """

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    session: PendingMemorySession
    existing_user_memory: UserMemory | None = None
    conversation_records: tuple[MemoryRecord, ...] = ()
    extracted_candidates: tuple[MemoryCandidate, ...] = ()
    important_candidates: tuple[MemoryCandidate, ...] = ()
    merged_user_memory: UserMemory | None = None
    saved: bool = False


def build_empty_profile() -> UserMemoryProfile:
    """构造一个空的用户画像对象，作为 merge 阶段的默认基线。"""

    return UserMemoryProfile()


def build_now() -> datetime:
    """统一生成当前 UTC 时间，便于节点层维护时间字段。"""

    return datetime.now(UTC)
