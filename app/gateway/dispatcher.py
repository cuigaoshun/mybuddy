from __future__ import annotations

import json
import logging

import lark_oapi as lark

from app.core.config import FeishuConfig
from app.event.models import IncomingChatMessage
from app.router.session_manager import SessionManager

LOGGER = logging.getLogger(__name__)


class FeishuDispatcher:
    def __init__(self, config: FeishuConfig, session_manager: SessionManager) -> None:
        self._config = config
        self._session_manager = session_manager

    def build_event_handler(self) -> lark.EventDispatcherHandler:
        """Create the Feishu websocket event handler."""
        return lark.EventDispatcherHandler.builder(
            "",
            "",
        ).register_p2_im_message_receive_v1(self._handle_message_received).build()

    def _handle_message_received(self, data: lark.im.v1.P2ImMessageReceiveV1) -> None:
        normalized_message = _normalize_message(data)
        if normalized_message is None:
            return

        LOGGER.info(
            "收到飞书消息，chat_id=%s message_id=%s text=%s",
            normalized_message.chat_id,
            normalized_message.message_id,
            normalized_message.text,
        )
        self._session_manager.handle_message(normalized_message)


def _normalize_message(data: lark.im.v1.P2ImMessageReceiveV1) -> IncomingChatMessage | None:
    message = data.event.message
    if message.message_type != "text":
        return None

    payload = json.loads(message.content)
    if not isinstance(payload, dict):
        return None

    text_value = payload.get("text")
    if not isinstance(text_value, str):
        return None

    sender_open_id = data.event.sender.sender_id.open_id
    if sender_open_id is None:
        return None

    return IncomingChatMessage(
        text=text_value.strip(),
        chat_id=message.chat_id,
        sender_open_id=sender_open_id,
        message_id=message.message_id,
        chat_type=message.chat_type,
    )
