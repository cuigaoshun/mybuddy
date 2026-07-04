from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Final

IM_TYPE_FEISHU: Final[str] = "feishu"


@dataclass(frozen=True, slots=True)
class IncomingChatMessage:
    """统一的入站消息模型。"""

    im_type: str  # IM 平台类型，例如 feishu
    text: str  # 当前归一化后的文本内容
    chat_id: str  # 会话标识
    sender_id: str  # 发送方标识
    message_id: str  # 平台消息标识
    chat_type: str  # 会话类型，例如 p2p、group
    message_time: datetime  # 消息时间，统一使用带时区时间
