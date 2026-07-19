from __future__ import annotations

from typing import Protocol

import lark_oapi as lark

from app.core.config import AppRuntimeConfig, FeishuConfig
from app.event.bus import EventBus
from app.gateway.dispatch import FeishuDispatcher, WeChatDispatcher
from app.router.session_manager import SessionManager
from app.storage.wechat_account_service import WeChatAccountService
from app.workers.wechat_poller import WeChatPollingRunner
from pkg.weixin import WeixinApiClient


class AppBootstrapContainer(Protocol):
    """应用启动链路所需的最小容器协议。"""

    def app_runtime_config(self) -> AppRuntimeConfig:
        ...

    def feishu_config(self) -> FeishuConfig:
        ...

    def event_bus(self) -> EventBus:
        ...

    def session_manager(self) -> SessionManager:
        ...

    def feishu_dispatcher(self) -> FeishuDispatcher:
        ...

    def feishu_client(self) -> lark.ws.Client:
        ...

    def wechat_dispatcher(self) -> WeChatDispatcher:
        ...

    def weixin_api_client(self) -> WeixinApiClient:
        ...

    def wechat_account_service(self) -> WeChatAccountService:
        ...

    def wechat_poller_runner(self) -> WeChatPollingRunner:
        ...
