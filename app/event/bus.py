from __future__ import annotations

from collections import defaultdict
from typing import Callable, DefaultDict, Final, TypeAlias

from app.event.models import IncomingChatMessage

MessageHandler: TypeAlias = Callable[[IncomingChatMessage], None]
INCOMING_CHAT_TOPIC: Final[str] = "incoming_chat"


class EventBus:
    def __init__(self) -> None:
        self._incoming_chat_handlers: DefaultDict[str, list[MessageHandler]] = defaultdict(list)

    def subscribe_incoming_chat(self, topic: str, handler: MessageHandler) -> None:
        self._incoming_chat_handlers[topic].append(handler)

    def publish_incoming_chat(self, topic: str, message: IncomingChatMessage) -> None:
        for handler in self._incoming_chat_handlers[topic]:
            handler(message)
