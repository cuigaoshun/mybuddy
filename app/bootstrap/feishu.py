from __future__ import annotations

import asyncio

import lark_oapi as lark
import lark_oapi.ws.client as lark_ws_client
from loguru import logger

from app.bootstrap.protocols import AppBootstrapContainer
from app.core.config import FeishuConfig
from app.core.log import configure_logging
from app.event.bus import EventBus, INCOMING_CHAT_TOPIC
from app.event.models import IM_TYPE_FEISHU


# 装配飞书 websocket client。
def create_feishu_client(container: AppBootstrapContainer) -> lark.ws.Client:
    """装配飞书 websocket client。"""
    feishu_config = container.feishu_config()
    if not isinstance(feishu_config, FeishuConfig):
        raise RuntimeError("FeishuConfig 未正确注入容器")

    configure_logging(feishu_config.log_level, feishu_config.log_dir)
    event_bus = container.event_bus()
    if not isinstance(event_bus, EventBus):
        raise RuntimeError("EventBus 未正确注入容器")

    session_manager = container.session_manager()
    event_bus.subscribe_incoming_chat(INCOMING_CHAT_TOPIC, IM_TYPE_FEISHU, session_manager.handle_message)
    dispatcher = container.feishu_dispatcher()

    return lark.ws.Client(
        feishu_config.app_id,
        feishu_config.app_secret,
        event_handler=dispatcher.build_event_handler(),
        log_level=_resolve_lark_log_level(feishu_config.log_level),
    )


async def start_listener(client: lark.ws.Client) -> None:
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, _start_client, client)


async def stop_listener(client: lark.ws.Client) -> None:
    close_method = getattr(client, "close", None)
    if close_method is None:
        return
    result = close_method()
    if asyncio.iscoroutine(result):
        await result


def _start_client(client: lark.ws.Client) -> None:
    thread_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(thread_loop)
    lark_ws_client.loop = thread_loop
    logger.info("启动飞书Client")
    client.start()


def _resolve_lark_log_level(log_level: str) -> lark.LogLevel:
    normalized_level = log_level.upper()
    if normalized_level == "DEBUG":
        return lark.LogLevel.DEBUG
    if normalized_level == "WARNING":
        return lark.LogLevel.WARNING
    if normalized_level == "ERROR":
        return lark.LogLevel.ERROR
    return lark.LogLevel.INFO
