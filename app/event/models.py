from __future__ import annotations

from dataclasses import dataclass
from dataclasses import replace
from datetime import datetime
from typing import Final

IM_TYPE_FEISHU: Final[str] = "feishu"
IM_TYPE_WECHAT: Final[str] = "wechat"


@dataclass(frozen=True, slots=True)
class WeixinIncomingMessageExtra:
    # 当前入站消息对应的微信 bot 账号 ID。
    bot_account_id: str | None = None
    # 当前消息可立即用于回复的上下文 token。
    context_token: str | None = None


@dataclass(frozen=True, slots=True)
class IncomingChatMessageExtra:
    # 平台专属补充字段按平台命名空间收口，避免污染顶层统一字段。
    weixin: WeixinIncomingMessageExtra | None = None


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
    # 平台专属补充元数据，不进入统一主文本字段。
    extra: IncomingChatMessageExtra | None = None

    def with_user_id(self, user_id: str) -> "IncomingChatMessage":
        return replace(self, user_id=user_id)
