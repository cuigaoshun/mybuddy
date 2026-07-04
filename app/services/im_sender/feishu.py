from __future__ import annotations

import json
from datetime import datetime, timezone

import lark_oapi as lark
from loguru import logger
from lark_oapi.api.im.v1 import CreateMessageRequest, CreateMessageRequestBody

from app.core.config import FeishuConfig
from app.event.models import IM_TYPE_FEISHU
from app.services.im_sender.errors import SendMessageError
from app.services.im_sender.models import SentMessageResult


class FeishuMessageSender:
    """飞书消息发送实现，负责封装飞书 SDK 调用细节。"""

    def __init__(self, config: FeishuConfig) -> None:
        """根据飞书配置初始化 SDK client。"""
        self._client = lark.Client.builder() \
            .app_id(config.app_id) \
            .app_secret(config.app_secret) \
            .log_level(_resolve_lark_log_level(config.log_level)) \
            .build()

    def send_text(self, chat_id: str, text: str) -> SentMessageResult:
        """发送一条飞书文本消息，并返回统一发送结果。"""
        request = CreateMessageRequest.builder() \
            .receive_id_type("chat_id") \
            .request_body(
                CreateMessageRequestBody.builder()
                .receive_id(chat_id)
                .msg_type("text")
                .content(json.dumps({"text": text}, ensure_ascii=False))
                .build(),
            ) \
            .build()

        response = self._client.im.v1.message.create(request)
        if response.success():
            logger.info("飞书消息发送成功，chat_id={chat_id}", chat_id=chat_id)
            return SentMessageResult(
                im_type=IM_TYPE_FEISHU,
                chat_id=chat_id,
                message_id=_resolve_message_id(response.data),
                content=text,
                message_time=_resolve_message_time(response.data),
            )

        logger.error(
            "飞书消息发送失败，chat_id={chat_id} code={code} msg={msg} log_id={log_id}",
            chat_id=chat_id,
            code=response.code,
            msg=response.msg,
            log_id=response.get_log_id(),
        )
        raise SendMessageError(chat_id, response.code, response.msg)


def _resolve_lark_log_level(log_level: str) -> lark.LogLevel:
    """把字符串日志级别转换成飞书 SDK 使用的枚举值。"""
    normalized_level = log_level.upper()
    if normalized_level == "DEBUG":
        return lark.LogLevel.DEBUG
    if normalized_level == "WARNING":
        return lark.LogLevel.WARNING
    if normalized_level == "ERROR":
        return lark.LogLevel.ERROR
    return lark.LogLevel.INFO


def _resolve_message_id(response_data: object) -> str:
    """从飞书发送响应里提取消息 ID。"""
    message_id = getattr(response_data, "message_id", None)
    if isinstance(message_id, str):
        return message_id
    return ""


def _resolve_message_time(response_data: object) -> datetime:
    """从飞书发送响应里提取消息时间；缺失时回退到当前 UTC 时间。"""
    create_time = getattr(response_data, "create_time", None)
    if isinstance(create_time, int):
        return datetime.fromtimestamp(create_time / 1000, tz=timezone.utc)
    if isinstance(create_time, str):
        normalized_value = create_time.strip()
        if normalized_value != "":
            try:
                return datetime.fromtimestamp(int(normalized_value) / 1000, tz=timezone.utc)
            except ValueError:
                pass

    return datetime.now(timezone.utc)
