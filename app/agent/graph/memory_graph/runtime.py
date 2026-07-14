from __future__ import annotations

"""长期记忆图运行时依赖定义。

这里不放业务逻辑，只定义图节点运行时共享的依赖对象，
确保节点层不直接从容器取对象，也不自行拼装外部资源。
"""

from dataclasses import dataclass

from app.agent.graph.main_graph.runtime import LLMProvider
from app.memory.service import ConversationMemoryService
from app.memory.session_info_service import ChatSessionInfoService
from app.memory.user_memory_service import UserMemoryService


@dataclass(frozen=True)
class MemoryGraphServices:
    """长期记忆处理图共享服务。

    这里只聚合长期记忆图真正需要的业务服务，
    避免节点直接感知底层仓储或容器装配细节。
    """

    conversation_memory_service: ConversationMemoryService
    chat_session_info_service: ChatSessionInfoService
    user_memory_service: UserMemoryService


@dataclass(frozen=True)
class MemoryGraphRuntimeContext:
    """长期记忆图节点共享的运行时依赖。

    和主图保持一致：模型能力和业务服务统一从 context 进入节点，
    节点只消费 context，不直接依赖容器。
    """

    llm_provider: LLMProvider
    services: MemoryGraphServices
