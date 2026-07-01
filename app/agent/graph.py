from __future__ import annotations

from typing import Final

from app.event.models import IncomingChatMessage

GREETING_TEXT: Final[str] = "你好"


def build_reply(message: IncomingChatMessage) -> str | None:
    """Return a reply for the supported hello demo."""
    if message.text == GREETING_TEXT:
        return GREETING_TEXT
    return None
