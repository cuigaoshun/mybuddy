from __future__ import annotations

from dataclasses import dataclass
from typing import Final

IM_TYPE_FEISHU: Final[str] = "feishu"


@dataclass(frozen=True, slots=True)
class IncomingChatMessage:
    im_type: str
    text: str
    chat_id: str
    sender_id: str
    message_id: str
    chat_type: str
