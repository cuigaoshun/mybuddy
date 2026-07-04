from __future__ import annotations

import asyncio
from dataclasses import dataclass

import lark_oapi as lark
import lark_oapi.ws.client as lark_ws_client
from loguru import logger

from app.bootstrap.protocols import FeishuBootstrapContainer
from app.core.config import FeishuConfig
from app.core.log import configure_logging
from app.event.bus import EventBus, INCOMING_CHAT_TOPIC
from app.event.models import IM_TYPE_FEISHU
from app.gateway.dispatch import FeishuDispatcher


class LarkService:
    """飞书客户端运行服务，负责异步启动与停止。"""

    def __init__(self, client) -> None:
        self.client = client

    async def start(self) -> None:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._start_client)

    async def stop(self) -> None:
        close_method = getattr(self.client, "close", None)
        if close_method is None:
            return
        result = close_method()
        if asyncio.iscoroutine(result):
            await result

    def _start_client(self) -> None:
        thread_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(thread_loop)
        lark_ws_client.loop = thread_loop
        self.client.start()


@dataclass(frozen=True, slots=True)
class FeishuAppRuntime:
    dispatcher: FeishuDispatcher


# 装配飞书消息链路依赖，返回飞书运行时对象。
def build_feishu_runtime(event_bus: EventBus, container: FeishuBootstrapContainer) -> FeishuAppRuntime:
    session_manager = container.session_manager()
    event_bus.subscribe_incoming_chat(INCOMING_CHAT_TOPIC, IM_TYPE_FEISHU, session_manager.handle_message)
    dispatcher = container.feishu_dispatcher()
    return FeishuAppRuntime(dispatcher=dispatcher)


def create_feishu_client(container: FeishuBootstrapContainer) -> lark.ws.Client:
    """装配飞书 websocket client。"""
    feishu_config = container.feishu_config()
    if not isinstance(feishu_config, FeishuConfig):
        raise RuntimeError("FeishuConfig 未正确注入容器")

    configure_logging(feishu_config.log_level, feishu_config.log_dir)
    event_bus = container.event_bus()
    if not isinstance(event_bus, EventBus):
        raise RuntimeError("EventBus 未正确注入容器")

    runtime = build_feishu_runtime(event_bus, container)

    logger.info("启动飞书Client")
    return lark.ws.Client(
        feishu_config.app_id,
        feishu_config.app_secret,
        event_handler=runtime.dispatcher.build_event_handler(),
        log_level=_resolve_lark_log_level(feishu_config.log_level),
    )


def _resolve_lark_log_level(log_level: str) -> lark.LogLevel:
    normalized_level = log_level.upper()
    if normalized_level == "DEBUG":
        return lark.LogLevel.DEBUG
    if normalized_level == "WARNING":
        return lark.LogLevel.WARNING
    if normalized_level == "ERROR":
        return lark.LogLevel.ERROR
    return lark.LogLevel.INFO
