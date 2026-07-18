from __future__ import annotations

from dataclasses import dataclass
from dataclasses import replace
from datetime import datetime
from typing import Final

IM_TYPE_FEISHU: Final[str] = "feishu"


@dataclass(frozen=True, slots=True)
class IncomingChatMessage:
    """统一的入站消息模型。"""

    im_type: str  # IM 平台类型，例如 feishu
    text: str  # 当前归一化后的文本内容
    chat_id: str  # 会话标识
    third_party_user_id: str  # 第三方平台用户标识，例如飞书 open_id
    message_id: str  # 平台消息标识
    chat_type: str  # 会话类型，例如 p2p、group
    message_time: datetime  # 消息时间，统一使用带时区时间
    user_id: str = ""  # 系统内部统一用户标识，进入主链路前为空字符串

    def with_user_id(self, user_id: str) -> "IncomingChatMessage":
        return replace(self, user_id=user_id)
