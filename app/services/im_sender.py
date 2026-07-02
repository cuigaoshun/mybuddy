from __future__ import annotations

import json

import lark_oapi as lark
from loguru import logger
from lark_oapi.api.im.v1 import CreateMessageRequest, CreateMessageRequestBody

from app.core.config import FeishuConfig


class SendMessageError(Exception):
    def __init__(self, chat_id: str, error_code: int, error_message: str) -> None:
        self.chat_id = chat_id
        self.error_code = error_code
        self.error_message = error_message
        super().__init__(chat_id, error_code, error_message)

    def __str__(self) -> str:
        return (
            f"飞书消息发送失败: chat_id={self.chat_id} "
            f"code={self.error_code} msg={self.error_message}"
        )


class FeishuMessageSender:
    def __init__(self, config: FeishuConfig) -> None:
        self._client = lark.Client.builder() \
            .app_id(config.app_id) \
            .app_secret(config.app_secret) \
            .log_level(_resolve_lark_log_level(config.log_level)) \
            .build()

    def send_text(self, chat_id: str, text: str) -> None:
        """Send a text message to the target chat."""
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
            return

        logger.error(
            "飞书消息发送失败，chat_id={chat_id} code={code} msg={msg} log_id={log_id}",
            chat_id=chat_id,
            code=response.code,
            msg=response.msg,
            log_id=response.get_log_id(),
        )
        raise SendMessageError(chat_id, response.code, response.msg)


def _resolve_lark_log_level(log_level: str) -> lark.LogLevel:
    normalized_level = log_level.upper()
    if normalized_level == "DEBUG":
        return lark.LogLevel.DEBUG
    if normalized_level == "WARNING":
        return lark.LogLevel.WARNING
    if normalized_level == "ERROR":
        return lark.LogLevel.ERROR
    return lark.LogLevel.INFO
