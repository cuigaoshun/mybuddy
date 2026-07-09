from __future__ import annotations

from dataclasses import dataclass

from app.agent.context.builder import ConversationContextBuilder
from app.agent.context.budget import ContextMessageBudgeter
from app.agent.context.formatter import ConversationContextFormatter
from app.agent.context.tools.registry import ToolRegistry
from app.memory.service import ConversationMemoryService
from app.services.llm import ChatModel
from app.services.web_search import ExaWebSearchService


@dataclass(frozen=True)
class LLMProvider:
    """统一提供图内使用的基础模型。"""

    # 保存当前图流程共享使用的基础聊天模型。
    base_model: ChatModel

    def model(self) -> ChatModel:
        # 返回图内节点统一复用的模型实例。
        return self.base_model


@dataclass(frozen=True)
class GraphRuntimeContext:
    """LangGraph 节点共享的运行时依赖。"""

    # 提供图内统一使用的基础模型访问入口。
    llm_provider: LLMProvider
    # 负责把当前消息和会话信息组装成上下文总包。
    context_builder: ConversationContextBuilder
    # 负责把结构化上下文格式化成模型消息序列。
    context_formatter: ConversationContextFormatter
    # 负责按模型上下文预算裁剪消息长度。
    context_budgeter: ContextMessageBudgeter
    # 统一提供核心工具与动态工具类别查询能力。
    tool_registry: ToolRegistry


@dataclass(frozen=True)
class GraphServices:
    """图装配阶段需要的业务服务聚合。"""

    conversation_memory_service: ConversationMemoryService
    web_search_service: ExaWebSearchService
