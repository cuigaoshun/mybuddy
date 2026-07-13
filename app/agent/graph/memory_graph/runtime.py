from __future__ import annotations

from dataclasses import dataclass

from app.agent.graph.main_graph.runtime import LLMProvider
from app.memory.service import ConversationMemoryService
from app.memory.session_info_service import ChatSessionInfoService
from app.memory.user_memory_service import UserMemoryService


@dataclass(frozen=True)
class MemoryGraphServices:
    """长期记忆处理图共享服务。"""

    conversation_memory_service: ConversationMemoryService
    chat_session_info_service: ChatSessionInfoService
    user_memory_service: UserMemoryService


@dataclass(frozen=True)
class MemoryGraphRuntimeContext:
    """长期记忆图节点共享的运行时依赖。"""

    llm_provider: LLMProvider
    services: MemoryGraphServices
