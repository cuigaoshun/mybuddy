from __future__ import annotations

from app.event.models import IM_TYPE_FEISHU, IM_TYPE_WECHAT
from app.services.im_sender.errors import SendMessageError
from app.services.im_sender.models import OutChatMessage, SentMessageResult


class CompositeMessageSender:
    """按平台路由到具体发送实现。"""

    def __init__(self, feishu_sender, wechat_sender) -> None:
        self._feishu_sender = feishu_sender
        self._wechat_sender = wechat_sender

    def send_text(self, message: OutChatMessage) -> SentMessageResult:
        if message.im_type == IM_TYPE_FEISHU:
            return self._feishu_sender.send_text(message)
        if message.im_type == IM_TYPE_WECHAT:
            return self._wechat_sender.send_text(message)
        raise SendMessageError(message.chat_id, 400, f"不支持的 IM 平台: {message.im_type}", im_type=message.im_type)

    def set_typing_status(self, message: OutChatMessage, is_typing: bool) -> None:
        if message.im_type == IM_TYPE_FEISHU:
            self._feishu_sender.set_typing_status(message, is_typing)
            return
        if message.im_type == IM_TYPE_WECHAT:
            self._wechat_sender.set_typing_status(message, is_typing)
            return
        raise SendMessageError(message.chat_id, 400, f"不支持的 IM 平台: {message.im_type}", im_type=message.im_type)
