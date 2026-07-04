from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass

import lark_oapi as lark
import lark_oapi.ws.client as lark_ws_client
from loguru import logger

from app.core.config import AppConfig
from app.core.config import get_config
from app.core.log import configure_logging
from app.event.bus import EventBus, INCOMING_CHAT_TOPIC
from app.event.models import IM_TYPE_FEISHU
from app.gateway.dispatch import FeishuDispatcher
from app.memory.embeddings import SentenceTransformerEmbeddingProvider
from app.memory.postgres_repository import PostgresConversationMemoryRepository
from app.memory.service import ConversationMemoryService
from app.router.session_manager import SessionManager
from app.services.im_sender import FeishuMessageSender

_feishu_thread: threading.Thread | None = None


@dataclass(frozen=True, slots=True)
class FeishuAppRuntime:
    dispatcher: FeishuDispatcher


# 装配飞书消息链路依赖，返回飞书运行时对象。
def build_feishu_runtime(config: AppConfig, event_bus: EventBus) -> FeishuAppRuntime:
    repository = PostgresConversationMemoryRepository(config.postgres)
    conversation_memory_service = ConversationMemoryService(
        embedding_provider=SentenceTransformerEmbeddingProvider(),
        repository=repository,
    )
    message_sender = FeishuMessageSender(config.feishu)
    session_manager = SessionManager(message_sender, conversation_memory_service)
    event_bus.subscribe_incoming_chat(INCOMING_CHAT_TOPIC, IM_TYPE_FEISHU, session_manager.handle_message)
    dispatcher = FeishuDispatcher(event_bus)
    return FeishuAppRuntime(dispatcher=dispatcher)


def start_feishu_bot(event_bus: EventBus) -> None:
    """Load config, wire dependencies, and start the Feishu websocket bot."""
    event_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(event_loop)
    lark_ws_client.loop = event_loop

    config = get_config()
    configure_logging(config.feishu.log_level, config.feishu.log_dir)
    runtime = build_feishu_runtime(config, event_bus)

    logger.info("飞书 hello bot 启动中")
    client = lark.ws.Client(
        config.feishu.app_id,
        config.feishu.app_secret,
        event_handler=runtime.dispatcher.build_event_handler(),
        log_level=_resolve_lark_log_level(config.feishu.log_level),
    )
    client.start()


def start_feishu_bot_in_background(event_bus: EventBus) -> None:
    """Start the Feishu bot in a background thread once."""
    global _feishu_thread

    if _feishu_thread is not None and _feishu_thread.is_alive():
        logger.info("飞书 hello bot 已经启动，跳过重复初始化")
        return

    _feishu_thread = threading.Thread(
        target=start_feishu_bot,
        args=(event_bus,),
        name="feishu-bot",
        daemon=True,
    )
    _feishu_thread.start()


def _resolve_lark_log_level(log_level: str) -> lark.LogLevel:
    normalized_level = log_level.upper()
    if normalized_level == "DEBUG":
        return lark.LogLevel.DEBUG
    if normalized_level == "WARNING":
        return lark.LogLevel.WARNING
    if normalized_level == "ERROR":
        return lark.LogLevel.ERROR
    return lark.LogLevel.INFO
