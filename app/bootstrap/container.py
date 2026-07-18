from __future__ import annotations

from dependency_injector import containers, providers
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.agent.graph.main_graph import GraphChatAgent, build_graph
from app.agent.graph.main_graph.runtime import GraphServices, LLMProvider
from app.agent.graph.memory_graph import MemoryGraphServices, build_memory_graph
from app.bootstrap.feishu import create_feishu_client
from app.bootstrap.listener import Listener
from app.bootstrap.postgres import get_engine
from app.core.config import AppRuntimeConfig, ExaConfig, LlmConfig
from app.event.bus import EventBus
from app.gateway.dispatch import FeishuDispatcher
from app.memory.embeddings import SentenceTransformerEmbeddingProvider
from app.memory.postgres import PostgresChatSessionInfoRepository, PostgresConversationMemoryRepository, PostgresUserMemoryRepository
from app.memory.service import ConversationMemoryService
from app.memory.session_info_service import ChatSessionInfoService
from app.memory.user_memory_service import UserMemoryService
from app.router.session_manager import SessionManager
from app.services.llm import create_chat_model
from app.services.im_sender import FeishuMessageSender
from app.services.web_search import ExaWebSearchService
from app.workers.memory_scheduler import MemorySchedulerRunner


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

    # Exa 配置对象。
    exa_config = providers.Dependency(instance_of=ExaConfig)

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

    # 聊天模型客户端，应用生命周期内复用。
    chat_model = providers.Singleton(create_chat_model, config=llm_config, runtime_config=app_runtime_config)

    # 图内模型提供者，统一暴露基础模型入口。
    llm_provider = providers.Singleton(LLMProvider, base_model=chat_model)

    # 网页搜索服务，应用生命周期内复用。
    web_search_service = providers.Singleton(ExaWebSearchService, config=exa_config)

    # 图装配阶段依赖的业务服务聚合。
    graph_services = providers.Singleton(
        GraphServices,
        conversation_memory_service=conversation_memory_service,
        user_memory_service=user_memory_service,
        web_search_service=web_search_service,
    )

    memory_graph_services = providers.Singleton(
        MemoryGraphServices,
        conversation_memory_service=conversation_memory_service,
        chat_session_info_service=chat_session_info_service,
        user_memory_service=user_memory_service,
    )

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

    # 聊天 Agent，负责把消息送进图并拿回最终回复。
    chat_agent = providers.Singleton(
        GraphChatAgent,
        compiled_graph=agent_graph,
    )

    # 飞书消息发送器。
    message_sender = providers.Singleton(FeishuMessageSender, feishu_config)

    # 会话编排器，每次取用时创建一个新实例。
    session_manager = providers.Factory(
        SessionManager,
        message_sender=message_sender,
        conversation_memory_service=conversation_memory_service,
        chat_session_info_service=chat_session_info_service,
        chat_agent=chat_agent,
    )

    # 飞书消息分发器，每次取用时创建一个新实例。
    feishu_dispatcher = providers.Factory(FeishuDispatcher, event_bus=event_bus)

    # 飞书 websocket client，应用生命周期内复用。
    feishu_client = providers.Singleton(create_feishu_client, container=__self__)

    # 监听器管理器，应用生命周期内复用。
    listener = providers.Singleton(Listener, container=__self__)

    memory_scheduler = providers.Singleton(AsyncIOScheduler)

    memory_scheduler_runner = providers.Singleton(
        MemorySchedulerRunner,
        scheduler=memory_scheduler,
        chat_session_info_service=chat_session_info_service,
        memory_graph=memory_graph,
    )
