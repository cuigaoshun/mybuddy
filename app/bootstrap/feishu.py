from __future__ import annotations

import asyncio
import logging
import threading

import lark_oapi as lark
import lark_oapi.ws.client as lark_ws_client

from app.core.config import get_config
from app.core.log import configure_logging
from app.gateway.dispatcher import FeishuDispatcher
from app.router.session_manager import SessionManager
from app.services.im_sender import FeishuMessageSender

LOGGER = logging.getLogger(__name__)
_feishu_thread: threading.Thread | None = None


def start_feishu_bot() -> None:
    """Load config, wire dependencies, and start the Feishu websocket bot."""
    event_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(event_loop)
    lark_ws_client.loop = event_loop

    config = get_config()
    configure_logging(config.feishu.log_level)

    sender = FeishuMessageSender(config.feishu)
    session_manager = SessionManager(sender)
    dispatcher = FeishuDispatcher(config.feishu, session_manager)

    LOGGER.info("飞书 hello bot 启动中")
    client = lark.ws.Client(
        config.feishu.app_id,
        config.feishu.app_secret,
        event_handler=dispatcher.build_event_handler(),
        log_level=_resolve_lark_log_level(config.feishu.log_level),
    )
    client.start()


def start_feishu_bot_in_background() -> None:
    """Start the Feishu bot in a background thread once."""
    global _feishu_thread

    if _feishu_thread is not None and _feishu_thread.is_alive():
        LOGGER.info("飞书 hello bot 已经启动，跳过重复初始化")
        return

    _feishu_thread = threading.Thread(
        target=start_feishu_bot,
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
