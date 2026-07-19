from __future__ import annotations

from dataclasses import dataclass

from app.agent.context.tool import ContextTool
from app.agent.context.tools.registry import ToolRegistry
from app.storage.service import ConversationMemoryService
from app.storage.user_memory_service import UserMemoryService
from app.services.llm import ChatModel
from app.services.web_search import WebSearchService


@dataclass(frozen=True)
class LLMProvider:
    """统一提供图内使用的基础模型。"""

    base_model: ChatModel

    def model(self) -> ChatModel:
        return self.base_model


@dataclass(frozen=True)
class GraphRuntimeContext:
    """LangGraph 节点共享的运行时依赖。"""

    llm_provider: LLMProvider
    services: GraphServices
    context_tool: ContextTool
    tool_registry: ToolRegistry


@dataclass(frozen=True)
class GraphServices:
    """图装配阶段需要的业务服务聚合。"""

    conversation_memory_service: ConversationMemoryService
    user_memory_service: UserMemoryService
    web_search_service: WebSearchService
