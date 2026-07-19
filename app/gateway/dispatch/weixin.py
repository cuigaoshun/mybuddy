from __future__ import annotations

from datetime import datetime, timezone

from app.core.config import AppRuntimeConfig
from app.event.bus import EventBus, INCOMING_CHAT_TOPIC
from app.event.models import IM_TYPE_WECHAT, IncomingChatMessage, IncomingChatMessageExtra, WeixinIncomingMessageExtra
from pkg.weixin.models import WeixinMessage, WeixinMessageItem


class WeChatDispatcher:
    """微信消息分发器，负责把长轮询结果归一化为内部消息模型。"""

    def __init__(self, event_bus: EventBus, runtime_config: AppRuntimeConfig) -> None:
        self._event_bus = event_bus
        self._runtime_config = runtime_config

    async def dispatch_raw_message(self, message: WeixinMessage, bot_account_id: str) -> None:
        # gateway 只做归一化和发布，不直接承担持久化职责。
        normalized_message = _normalize_message(message, bot_account_id)
        if normalized_message is None:
            return
        if self._runtime_config.is_development:
            logger_message = (
                "微信消息归一化完成，bot_account_id={bot_account_id} chat_id={chat_id} text={text}"
            )
            from loguru import logger
            logger.debug(
                logger_message,
                bot_account_id=bot_account_id,
                chat_id=normalized_message.chat_id,
                text=normalized_message.text,
            )
        await self._event_bus.publish_incoming_chat(INCOMING_CHAT_TOPIC, normalized_message)


def _normalize_message(message: WeixinMessage, bot_account_id: str) -> IncomingChatMessage | None:
    # 当前只接收入站用户消息，bot 自己发出的消息不进入主回复链路。
    if message.message_type != 1:
        return None

    third_party_user_id = message.from_user_id
    if not isinstance(third_party_user_id, str) or third_party_user_id == "":
        return None

    # 微信当前没有稳定返回 session_id，这里直接用对端 ID 作为统一 chat_id。
    chat_id = third_party_user_id

    if message.message_id == "":
        return None
    message_time = _parse_message_time(message.create_time_ms)
    if message_time is None:
        return None

    # 统一把平台 item_list 抽成主文本字段，额外平台信息走 extra.weixin。
    text = _extract_text(message.item_list)
    if text == "":
        return None

    weixin_extra = WeixinIncomingMessageExtra(
        bot_account_id=bot_account_id,
        context_token=message.context_token if isinstance(message.context_token, str) else None,
    )
    return IncomingChatMessage(
        im_type=IM_TYPE_WECHAT,
        text=text,
        chat_id=chat_id,
        third_party_user_id=third_party_user_id,
        message_id=message.message_id,
        chat_type="p2p",
        message_time=message_time,
        extra=IncomingChatMessageExtra(weixin=weixin_extra),
    )


def _parse_message_time(raw_value: object) -> datetime | None:
    # 微信侧消息时间是毫秒时间戳，这里统一归一化成 UTC 时间。
    if isinstance(raw_value, int):
        return datetime.fromtimestamp(raw_value / 1000, tz=timezone.utc)
    if isinstance(raw_value, str):
        normalized = raw_value.strip()
        if normalized == "":
            return None
        try:
            return datetime.fromtimestamp(int(normalized) / 1000, tz=timezone.utc)
        except ValueError:
            return None
    return None


def _extract_text(raw_items: tuple[WeixinMessageItem, ...]) -> str:
    # 一期先把平台多媒体消息降级成可读占位文本，保持主链路仍然以 text 为中心。
    parts: list[str] = []
    for raw_item in raw_items:
        item_type = raw_item.item_type
        if item_type == 1:
            text_value = raw_item.text_item.text if raw_item.text_item is not None else None
            if isinstance(text_value, str) and text_value.strip() != "":
                parts.append(text_value.strip())
        elif item_type == 2:
            parts.append("[image]")
        elif item_type == 3:
            if raw_item.voice_item is not None and isinstance(raw_item.voice_item.text, str) and raw_item.voice_item.text.strip() != "":
                parts.append(raw_item.voice_item.text.strip())
                continue
            parts.append("[voice]")
        elif item_type == 4:
            if raw_item.file_item is not None and isinstance(raw_item.file_item.file_name, str) and raw_item.file_item.file_name.strip() != "":
                parts.append(raw_item.file_item.file_name.strip())
                continue
            parts.append("[file]")
        elif item_type == 5:
            parts.append("[video]")
    return "\n".join(parts)
