from __future__ import annotations

from dependency_injector import containers, providers
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.agent.graph.main_graph import GraphChatAgent, build_graph
from app.agent.graph.main_graph.runtime import GraphServices, LLMProvider
from app.agent.graph.reminder_graph import ReminderGraphServices, build_reminder_graph
from app.agent.graph.memory_graph import MemoryGraphServices, build_memory_graph
from app.bootstrap.feishu import create_feishu_client
from app.bootstrap.listener import Listener
from app.bootstrap.postgres import get_engine
from app.bootstrap.wechat import create_wechat_poller_runner
from app.core.config import AppRuntimeConfig, LlmConfig, WebSearchConfig
from app.event.bus import EventBus
from app.gateway.dispatch import FeishuDispatcher, WeChatDispatcher
from app.services.reminder_execution import ReminderExecutionService
from app.storage.embeddings import SentenceTransformerEmbeddingProvider
from app.storage.postgres import PostgresReminderRepository
from app.storage.postgres import (
    PostgresChatSessionInfoRepository,
    PostgresConversationMemoryRepository,
    PostgresUserIdentityRepository,
    PostgresWeChatAccountRepository,
    PostgresUserMemoryRepository,
)
from app.storage.reminder_repository import ReminderRepository
from app.storage.reminder_service import ReminderService
from app.storage.service import ConversationMemoryService
from app.storage.session_info_service import ChatSessionInfoService
from app.storage.user_identity_service import UserIdentityService
from app.storage.user_memory_service import UserMemoryService
from app.storage.wechat_account_service import WeChatAccountService
from app.router.session_manager import SessionManager
from app.services.llm import create_chat_model
from app.services.im_sender import CompositeMessageSender, FeishuMessageSender, WeChatMessageSender
from app.services.web_search import WebSearchService
from app.workers.memory_scheduler import MemorySchedulerRunner
from app.workers.reminder_scheduler import ReminderSchedulerRunner
from app.pkg.weixin import WeixinApiClient


class AppContainer(containers.DeclarativeContainer):
    """应用级依赖注入容器。"""

    __self__ = providers.Self()

    # 飞书平台配置对象。
    app_runtime_config = providers.Dependency(instance_of=AppRuntimeConfig)

    # 飞书平台配置对象。
    feishu_config = providers.Dependency()

    # PostgreSQL 配置对象。
    postgres_config = providers.Dependency()

    # LLM 配置对象。
    llm_config = providers.Dependency(instance_of=LlmConfig)

    # 网页搜索配置对象。
    web_search_config = providers.Dependency(instance_of=WebSearchConfig)

    # 全局事件总线对象。
    event_bus = providers.Dependency(instance_of=EventBus)

    # 应用级数据库 Engine。
    engine = providers.Singleton(get_engine, postgres_config)

    # 向量模型提供者，应用生命周期内复用。
    embedding_provider = providers.Singleton(SentenceTransformerEmbeddingProvider)

    # 对话记忆 PostgreSQL 仓储。
    conversation_memory_repository = providers.Singleton(PostgresConversationMemoryRepository, engine=engine)

    # 会话信息 PostgreSQL 仓储。
    chat_session_info_repository = providers.Singleton(PostgresChatSessionInfoRepository, engine=engine)

    # 用户长期记忆 PostgreSQL 仓储。
    user_memory_repository = providers.Singleton(PostgresUserMemoryRepository, engine=engine)

    # 用户身份映射 PostgreSQL 仓储。
    user_identity_repository = providers.Singleton(PostgresUserIdentityRepository, engine=engine)

    reminder_repository: providers.Provider[ReminderRepository] = providers.Singleton(PostgresReminderRepository, engine=engine)

    # 微信账号运行态 PostgreSQL 仓储。
    wechat_account_repository = providers.Singleton(PostgresWeChatAccountRepository, engine=engine)

    # 对话记忆服务，负责文本提取与向量写入。
    conversation_memory_service = providers.Singleton(
        ConversationMemoryService,
        embedding_provider=embedding_provider,
        repository=conversation_memory_repository,
    )

    # 会话信息服务，负责维护最新回复时间等会话级信息。
    chat_session_info_service = providers.Singleton(
        ChatSessionInfoService,
        repository=chat_session_info_repository,
    )

    # 用户长期记忆服务，负责读取独立长期记忆快照。
    user_memory_service = providers.Singleton(
        UserMemoryService,
        repository=user_memory_repository,
    )

    # 用户身份解析服务，负责把第三方身份映射成系统 user_id。
    user_identity_service = providers.Singleton(
        UserIdentityService,
        repository=user_identity_repository,
    )

    # 微信账号运行态服务，统一维护扫码状态、账号状态和当前上下文缓存。
    wechat_account_service = providers.Singleton(
        WeChatAccountService,
        repository=wechat_account_repository,
        user_identity_service=user_identity_service,
    )

    reminder_service = providers.Singleton(
        ReminderService,
        repository=reminder_repository,
        runtime_config=app_runtime_config,
    )

    # 聊天模型客户端，应用生命周期内复用。
    chat_model = providers.Singleton(create_chat_model, config=llm_config, runtime_config=app_runtime_config)

    # 图内模型提供者，统一暴露基础模型入口。
    llm_provider = providers.Singleton(LLMProvider, base_model=chat_model)

    # 网页搜索服务，应用生命周期内复用。
    web_search_service = providers.Singleton(WebSearchService, config=web_search_config)

    # 图装配阶段依赖的业务服务聚合。
    graph_services = providers.Singleton(
        GraphServices,
        conversation_memory_service=conversation_memory_service,
        user_memory_service=user_memory_service,
        web_search_service=web_search_service,
        reminder_service=reminder_service,
    )

    memory_graph_services = providers.Singleton(
        MemoryGraphServices,
        conversation_memory_service=conversation_memory_service,
        chat_session_info_service=chat_session_info_service,
        user_memory_service=user_memory_service,
    )

    reminder_graph_services = providers.Singleton(ReminderGraphServices, llm_provider=llm_provider)

    # 编译后的 LangGraph，应用生命周期内复用。
    agent_graph = providers.Singleton(
        build_graph,
        llm_provider=llm_provider,
        service=graph_services,
    )

    memory_graph = providers.Singleton(
        build_memory_graph,
        llm_provider=llm_provider,
        services=memory_graph_services,
    )

    reminder_graph = providers.Singleton(
        build_reminder_graph,
        services=reminder_graph_services,
    )

    # 聊天 Agent，负责把消息送进图并拿回最终回复。
    chat_agent = providers.Singleton(
        GraphChatAgent,
        compiled_graph=agent_graph,
    )

    # 飞书消息发送器。
    feishu_message_sender = providers.Singleton(FeishuMessageSender, feishu_config)

    # 微信 API 低层 client，统一收口二维码、长轮询、发送与 typing 请求。
    weixin_api_client = providers.Singleton(WeixinApiClient)

    # 微信发送器，负责把统一出站对象翻译成微信协议请求。
    wechat_message_sender = providers.Singleton(
        WeChatMessageSender,
        client=weixin_api_client,
        wechat_account_service=wechat_account_service,
        runtime_config=app_runtime_config,
    )

    # 统一 sender 根据 im_type 分发到飞书或微信实现。
    message_sender = providers.Singleton(
        CompositeMessageSender,
        feishu_sender=feishu_message_sender,
        wechat_sender=wechat_message_sender,
    )

    reminder_execution_service = providers.Singleton(
        ReminderExecutionService,
        repository=reminder_repository,
        reminder_service=reminder_service,
        reminder_graph=reminder_graph,
        message_sender=message_sender,
        conversation_memory_service=conversation_memory_service,
        wechat_account_service=wechat_account_service,
    )

    # 会话编排器，每次取用时创建一个新实例。
    session_manager = providers.Factory(
        SessionManager,
        message_sender=message_sender,
        conversation_memory_service=conversation_memory_service,
        chat_session_info_service=chat_session_info_service,
        user_identity_service=user_identity_service,
        chat_agent=chat_agent,
    )

    # 飞书消息分发器，每次取用时创建一个新实例。
    feishu_dispatcher = providers.Factory(FeishuDispatcher, event_bus=event_bus)

    # 微信入站分发器负责做统一归一化并发布到事件总线。
    wechat_dispatcher = providers.Factory(
        WeChatDispatcher,
        event_bus=event_bus,
        runtime_config=app_runtime_config,
    )

    # 飞书 websocket client，应用生命周期内复用。
    feishu_client = providers.Singleton(create_feishu_client, container=__self__)

    # 微信长轮询 runner 在应用启动时按活跃账号统一拉起。
    wechat_poller_runner = providers.Singleton(create_wechat_poller_runner, container=__self__)

    # 监听器管理器，应用生命周期内复用。
    listener = providers.Singleton(Listener, container=__self__)

    memory_scheduler = providers.Singleton(AsyncIOScheduler)
    reminder_scheduler = providers.Singleton(AsyncIOScheduler)

    memory_scheduler_runner = providers.Singleton(
        MemorySchedulerRunner,
        scheduler=memory_scheduler,
        chat_session_info_service=chat_session_info_service,
        memory_graph=memory_graph,
    )

    reminder_scheduler_runner = providers.Singleton(
        ReminderSchedulerRunner,
        scheduler=reminder_scheduler,
        reminder_service=reminder_service,
        reminder_execution_service=reminder_execution_service,
    )
