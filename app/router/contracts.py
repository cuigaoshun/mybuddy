from __future__ import annotations

from typing import Protocol

from app.event.models import IncomingChatMessage
from app.storage.models import ChatSessionInfo
from app.services.im_sender.models import OutChatMessage, SentMessageResult


class MessageSender(Protocol):
    """统一发送消息协议，向路由层屏蔽具体 IM 实现。"""

    def send_text(self, message: OutChatMessage) -> SentMessageResult:
        ...

    def set_typing_status(self, message: OutChatMessage, is_typing: bool) -> None:
        ...


class ChatAgent(Protocol):
    """统一聊天 Agent 协议，向路由层屏蔽具体回复实现。"""

    def generate_reply(self, message: IncomingChatMessage, session_info: ChatSessionInfo) -> str | None:
        ...
