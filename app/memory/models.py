from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Final

TEXT_CONTENT_TYPE: Final[str] = "text"

USER_MESSAGE_TYPE: Final[int] = 0
ASSISTANT_MESSAGE_TYPE: Final[int] = 1


@dataclass(frozen=True, slots=True)
class MemoryRecord:
    """对话记忆记录模型。"""

    user_id: str  # 用户标识，当前一期使用飞书 sender_id
    chat_id: str  # 会话标识
    message_id: str  # 消息标识，用于去重
    message_type: int  # 消息方向，0 表示用户消息，1 表示助手消息
    im_type: str  # IM 平台类型，例如 feishu
    message_time: datetime  # 消息时间，统一使用带时区时间
    content_type: str  # 内容类型，一期固定为 text
    content: dict[str, object]  # JSON 内容，一期结构为 {"text": "..."}


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
