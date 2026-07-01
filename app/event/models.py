from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class IncomingChatMessage:
    text: str
    chat_id: str
    sender_open_id: str
    message_id: str
    chat_type: str
