from __future__ import annotations

from dependency_injector import containers, providers

from app.agent.graph import GraphChatAgent, build_graph
from app.bootstrap.feishu import create_feishu_client
from app.bootstrap.listener import Listener
from app.bootstrap.postgres import get_engine
from app.core.config import LlmConfig
from app.event.bus import EventBus
from app.gateway.dispatch import FeishuDispatcher
from app.memory.embeddings import SentenceTransformerEmbeddingProvider
from app.memory.postgres_repository import PostgresConversationMemoryRepository
from app.memory.postgres_session_info_repository import PostgresChatSessionInfoRepository
from app.memory.service import ConversationMemoryService
from app.memory.session_info_service import ChatSessionInfoService
from app.router.session_manager import SessionManager
from app.services.llm import create_chat_model
from app.services.im_sender import FeishuMessageSender


class AppContainer(containers.DeclarativeContainer):
    """应用级依赖注入容器。"""

    __self__ = providers.Self()

    # 飞书平台配置对象。
    feishu_config = providers.Dependency()

    # PostgreSQL 配置对象。
    postgres_config = providers.Dependency()

    # LLM 配置对象。
    llm_config = providers.Dependency(instance_of=LlmConfig)

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

    # 聊天模型客户端，应用生命周期内复用。
    chat_model = providers.Singleton(create_chat_model, config=llm_config)

    # 编译后的 LangGraph，应用生命周期内复用。
    agent_graph = providers.Singleton(
        build_graph,
        chat_model=chat_model,
    )

    # 聊天 Agent，负责读取最近记忆并调用图。
    chat_agent = providers.Singleton(
        GraphChatAgent,
        conversation_memory_service=conversation_memory_service,
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
