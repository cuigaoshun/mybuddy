from __future__ import annotations

from dependency_injector import containers, providers

from app.bootstrap.feishu import LarkService
from app.bootstrap.postgres import get_engine
from app.event.bus import EventBus
from app.gateway.dispatch import FeishuDispatcher
from app.memory.embeddings import SentenceTransformerEmbeddingProvider
from app.memory.postgres_repository import PostgresConversationMemoryRepository
from app.memory.service import ConversationMemoryService
from app.router.session_manager import SessionManager
from app.services.im_sender import FeishuMessageSender


class AppContainer(containers.DeclarativeContainer):
    """应用级依赖注入容器。"""

    # 飞书平台配置对象。
    feishu_config = providers.Dependency()

    # PostgreSQL 配置对象。
    postgres_config = providers.Dependency()

    # 全局事件总线对象。
    event_bus = providers.Dependency(instance_of=EventBus)

    # 应用级数据库 Engine。
    engine = providers.Singleton(get_engine, postgres_config)

    # 向量模型提供者，应用生命周期内复用。
    embedding_provider = providers.Singleton(SentenceTransformerEmbeddingProvider)

    # 对话记忆 PostgreSQL 仓储。
    conversation_memory_repository = providers.Singleton(PostgresConversationMemoryRepository, engine=engine)

    # 对话记忆服务，负责文本提取与向量写入。
    conversation_memory_service = providers.Singleton(
        ConversationMemoryService,
        embedding_provider=embedding_provider,
        repository=conversation_memory_repository,
    )

    # 飞书消息发送器。
    message_sender = providers.Singleton(FeishuMessageSender, feishu_config)

    # 会话编排器，每次取用时创建一个新实例。
    session_manager = providers.Factory(
        SessionManager,
        message_sender=message_sender,
        conversation_memory_service=conversation_memory_service,
    )

    # 飞书消息分发器，每次取用时创建一个新实例。
    feishu_dispatcher = providers.Factory(FeishuDispatcher, event_bus=event_bus)
