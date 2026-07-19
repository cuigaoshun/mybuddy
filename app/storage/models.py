from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Final

TEXT_CONTENT_TYPE: Final[str] = "text"

USER_MESSAGE_TYPE: Final[int] = 0
ASSISTANT_MESSAGE_TYPE: Final[int] = 1


@dataclass(frozen=True, slots=True)
class MemoryRecord:
    """对话记忆记录模型。"""

    user_id: str  # 系统内部统一用户标识
    chat_id: str  # 会话标识
    message_id: str  # 消息标识，用于去重
    message_type: int  # 消息方向，0 表示用户消息，1 表示助手消息
    im_type: str  # IM 平台类型，例如 feishu
    message_time: datetime  # 消息时间，统一使用带时区时间
    content_type: str  # 内容类型，一期固定为 text
    content: dict[str, object]  # JSON 内容，一期结构为 {"text": "..."}


@dataclass(frozen=True, slots=True)
class RetrievedMemoryHit:
    record: MemoryRecord
    score: float


@dataclass(frozen=True, slots=True)
class ChatSessionInfo:
    """会话详情模型，承载会话级元信息与租约状态。"""

    user_id: str
    im_type: str
    chat_id: str
    first_reply_time: datetime | None = None
    latest_reply_time: datetime | None = None
    lease_owner: str | None = None
    lease_until: datetime | None = None


@dataclass(frozen=True, slots=True)
class UserMemoryAttribute:
    """用户属性中的一条键值项。"""

    key: str
    value: str | bool | int | float


@dataclass(frozen=True, slots=True)
class UserMemoryAttributes:
    """一组结构化用户属性。"""

    items: tuple[UserMemoryAttribute, ...] = ()

    def to_dict(self) -> dict[str, str | bool | int | float]:
        return {item.key: item.value for item in self.items}


@dataclass(frozen=True, slots=True)
class UserMemoryAffinity:
    """用户与 Agent 关系中的好感度结构。"""

    level: int | None = None
    confidence: float | None = None
    updated_at: datetime | None = None
    notes: str | None = None

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {}
        if self.level is not None:
            payload["level"] = self.level
        if self.confidence is not None:
            payload["confidence"] = self.confidence
        if self.notes:
            payload["notes"] = self.notes
        return payload


@dataclass(frozen=True, slots=True)
class UserMemoryRelationship:
    """用户与 Agent 的关系状态。"""

    affinity: UserMemoryAffinity | None = None

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {}
        if self.affinity is not None:
            affinity_payload = self.affinity.to_dict()
            if affinity_payload:
                payload["affinity"] = affinity_payload
        return payload


@dataclass(frozen=True, slots=True)
class UserMemoryProfile:
    """结构化用户画像。"""

    profile: UserMemoryAttributes = field(default_factory=UserMemoryAttributes)
    preferences: UserMemoryAttributes = field(default_factory=UserMemoryAttributes)
    relationship: UserMemoryRelationship = field(default_factory=UserMemoryRelationship)

    def to_dict(self) -> dict[str, object]:
        return {
            "profile": self.profile.to_dict(),
            "preferences": self.preferences.to_dict(),
            "relationship": self.relationship.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class UserMemory:
    """用户级长期记忆快照。"""

    user_id: str
    im_type: str
    long_term_memory_summary: str | None
    user_profile: UserMemoryProfile
    last_processed_message_id: str | None
    version: int
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class PendingMemorySession:
    """待做长期记忆整理的会话。"""

    user_id: str
    im_type: str
    chat_id: str
    latest_reply_time: datetime


@dataclass(frozen=True, slots=True)
class ConversationHistoryQuery:
    """历史消息查询条件。"""

    user_id: str
    im_type: str
    chat_id: str
    text: str
    start_time: datetime | None = None
    end_time: datetime | None = None
    limit: int = 5


@dataclass(frozen=True, slots=True)
class HistorySearchResult:
    """历史消息命中结果，包含命中来源信息。"""

    record: MemoryRecord
    matched_by_text: bool
    matched_by_vector: bool


@dataclass(frozen=True, slots=True)
class ExternalUserIdentity:
    """第三方平台身份与系统 user_id 的绑定关系。"""

    user_id: str
    im_type: str
    third_party_user_id: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class WeChatAccount:
    """微信账号运行态快照。"""

    qrcode: str
    qrcode_status: str
    user_id: str | None = None
    bot_account_id: str | None = None
    third_party_user_id: str | None = None
    bot_token: str | None = None
    get_updates_buf: str | None = None
    context_token: str | None = None
    typing_ticket: str | None = None
    source_message_id: str | None = None
    is_active: bool = True
    logged_in_at: datetime | None = None
    qrcode_updated_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
