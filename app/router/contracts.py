from __future__ import annotations

from typing import Protocol

from app.event.models import IncomingChatMessage
from app.memory.models import ChatSessionInfo


class MessageSender(Protocol):
    """统一发送消息协议，向路由层屏蔽具体 IM 实现。"""

    def send_text(self, chat_id: str, text: str):
        ...


class ChatAgent(Protocol):
    """统一聊天 Agent 协议，向路由层屏蔽具体回复实现。"""

    def generate_reply(self, message: IncomingChatMessage, session_info: ChatSessionInfo) -> str | None:
        ...
