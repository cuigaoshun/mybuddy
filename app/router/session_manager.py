from __future__ import annotations

from typing import Protocol

from app.agent.graph import build_reply
from app.event.models import IncomingChatMessage


class MessageSender(Protocol):
    def send_text(self, chat_id: str, text: str) -> None:
        ...


class SessionManager:
    def __init__(self, message_sender: MessageSender) -> None:
        self._message_sender = message_sender

    def handle_message(self, message: IncomingChatMessage) -> None:
        """Handle one normalized chat message."""
        reply_text = build_reply(message)
        if reply_text is None:
            return

        self._message_sender.send_text(message.chat_id, reply_text)
