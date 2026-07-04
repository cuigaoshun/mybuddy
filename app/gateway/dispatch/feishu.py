from __future__ import annotations

import json
from json import JSONDecodeError
from datetime import datetime, timezone
from typing import Final

import lark_oapi as lark
from loguru import logger

from app.event.bus import EventBus, INCOMING_CHAT_TOPIC
from app.event.models import IM_TYPE_FEISHU, IncomingChatMessage

TEXT_MESSAGE_TYPE: Final[str] = "text"


class FeishuDispatcher:
    """飞书消息分发器，负责接收事件并发布内部消息。"""

    def __init__(self, event_bus: EventBus) -> None:
        """注入事件总线，用于向内部路由层转发消息。"""
        self._event_bus = event_bus

    def build_event_handler(self) -> lark.EventDispatcherHandler:
        """构建飞书 websocket 事件处理器。"""
        return lark.EventDispatcherHandler.builder(
            "",
            "",
        ).register_p2_im_message_receive_v1(self._handle_message_received).build()

    def _handle_message_received(self, data: lark.im.v1.P2ImMessageReceiveV1) -> None:
        """接收飞书事件并转换成内部统一消息后发布。"""
        normalized_message = _normalize_message(data)
        if normalized_message is None:
            return

        logger.info(
            "收到飞书消息，chat_id={chat_id} message_id={message_id} text={text}",
            chat_id=normalized_message.chat_id,
            message_id=normalized_message.message_id,
            text=normalized_message.text,
        )
        self._event_bus.publish_incoming_chat(INCOMING_CHAT_TOPIC, normalized_message)


def _normalize_message(data: lark.im.v1.P2ImMessageReceiveV1) -> IncomingChatMessage | None:
    """把飞书原始消息事件归一化为内部消息模型。"""
    message = data.event.message
    if message.message_type != TEXT_MESSAGE_TYPE:
        return None

    try:
        payload = json.loads(message.content)
    except JSONDecodeError:
        logger.warning("飞书消息内容不是合法 JSON，message_id={message_id}", message_id=message.message_id)
        return None
    if not isinstance(payload, dict):
        return None

    text_value = payload.get("text")
    if not isinstance(text_value, str):
        return None

    sender_id = data.event.sender.sender_id.open_id
    if sender_id is None:
        return None

    message_time = _parse_feishu_message_time(message.create_time)
    if message_time is None:
        return None

    return IncomingChatMessage(
        im_type=IM_TYPE_FEISHU,
        text=text_value.strip(),
        chat_id=message.chat_id,
        sender_id=sender_id,
        message_id=message.message_id,
        chat_type=message.chat_type,
        message_time=message_time,
    )


def _parse_feishu_message_time(raw_value: object) -> datetime | None:
    """把飞书毫秒时间转换成 UTC 时区时间。"""
    if isinstance(raw_value, int):
        return datetime.fromtimestamp(raw_value / 1000, tz=timezone.utc)

    if isinstance(raw_value, str):
        normalized_value = raw_value.strip()
        if normalized_value == "":
            return None
        try:
            return datetime.fromtimestamp(int(normalized_value) / 1000, tz=timezone.utc)
        except ValueError:
            return None

    return None
