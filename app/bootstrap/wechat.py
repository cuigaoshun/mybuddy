from __future__ import annotations

from app.bootstrap.protocols import AppBootstrapContainer
from app.event.bus import EventBus, INCOMING_CHAT_TOPIC
from app.event.models import IM_TYPE_WECHAT
from app.workers.wechat_poller import WeChatPollingRunner


def create_wechat_poller_runner(container: AppBootstrapContainer) -> WeChatPollingRunner:
    # 微信入站消息和飞书一样，最终都订阅到统一 incoming_chat topic。
    event_bus = container.event_bus()
    if not isinstance(event_bus, EventBus):
        raise RuntimeError("EventBus 未正确注入容器")

    session_manager = container.session_manager()
    event_bus.subscribe_incoming_chat(INCOMING_CHAT_TOPIC, IM_TYPE_WECHAT, session_manager.handle_message)
    # runner 只依赖三件事：API client、运行态 service、dispatcher。
    return WeChatPollingRunner(
        client=container.weixin_api_client(),
        wechat_account_service=container.wechat_account_service(),
        dispatcher=container.wechat_dispatcher(),
        runtime_config=container.app_runtime_config(),
    )
