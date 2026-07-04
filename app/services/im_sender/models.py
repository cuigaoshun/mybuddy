from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class SentMessageResult:
    """统一的发送结果模型。"""

    im_type: str  # IM 平台类型，例如 feishu
    chat_id: str  # 发送目标会话标识
    message_id: str  # 平台返回的消息标识
    content: str  # 实际发送出去的文本内容
    message_time: datetime  # 平台返回的消息时间，统一使用带时区时间
