from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class WeixinOutChatExtra:
    # 出站消息如果已经知道 bot 账号，可直接透传给 sender 做精确定位。
    bot_account_id: str | None = None
    # 当前消息即时可用的 context_token。
    context_token: str | None = None


@dataclass(frozen=True, slots=True)
class OutChatMessageExtra:
    # 平台专属出站元数据按平台命名空间隔离。
    weixin: WeixinOutChatExtra | None = None


@dataclass(frozen=True, slots=True)
class OutChatMessage:
    """统一的出站消息模型。"""

    # 发送目标所属 IM 平台。
    im_type: str
    # 发送正文，当前统一发送层仍以文本为主。
    text: str
    # 统一会话标识。
    chat_id: str
    # 第三方平台用户标识。
    third_party_user_id: str
    # 会话类型，例如 p2p、group。
    chat_type: str
    # 系统内部统一用户标识。
    user_id: str
    # 平台专属补充出站信息。
    extra: OutChatMessageExtra | None = None


@dataclass(frozen=True, slots=True)
class SentMessageResult:
    """统一的发送结果模型。"""

    im_type: str  # IM 平台类型，例如 feishu
    chat_id: str  # 发送目标会话标识
    message_id: str  # 平台返回的消息标识
    content: str  # 实际发送出去的文本内容
    message_time: datetime  # 平台返回的消息时间，统一使用带时区时间
