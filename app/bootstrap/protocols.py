from __future__ import annotations

from typing import Protocol

from app.core.config import FeishuConfig
from app.event.bus import EventBus
from app.gateway.dispatch import FeishuDispatcher
from app.router.session_manager import SessionManager


class FeishuBootstrapContainer(Protocol):
    """飞书启动链路所需的最小容器协议。"""

    def feishu_config(self) -> FeishuConfig:
        ...

    def event_bus(self) -> EventBus:
        ...

    def session_manager(self) -> SessionManager:
        ...

    def feishu_dispatcher(self) -> FeishuDispatcher:
        ...
