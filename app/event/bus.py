from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Callable, DefaultDict, Final, TypeAlias

from app.event.models import IncomingChatMessage

MessageHandler: TypeAlias = Callable[[IncomingChatMessage], None]
INCOMING_CHAT_TOPIC: Final[str] = "incoming_chat"


@dataclass(frozen=True, slots=True)
class IncomingChatSubscription:
    im_type: str
    handler: MessageHandler


class EventBus:
    def __init__(self) -> None:
        self._incoming_chat_handlers: DefaultDict[str, list[IncomingChatSubscription]] = defaultdict(list)

    def subscribe_incoming_chat(self, topic: str, im_type: str, handler: MessageHandler) -> None:
        subscription = IncomingChatSubscription(im_type=im_type, handler=handler)
        if subscription in self._incoming_chat_handlers[topic]:
            return

        self._incoming_chat_handlers[topic].append(subscription)

    def publish_incoming_chat(self, topic: str, message: IncomingChatMessage) -> None:
        for subscription in self._incoming_chat_handlers[topic]:
            if subscription.im_type != message.im_type:
                continue
            subscription.handler(message)
