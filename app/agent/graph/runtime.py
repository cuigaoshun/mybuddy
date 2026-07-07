from __future__ import annotations

from dataclasses import dataclass

from app.agent.context.builder import ConversationContextBuilder
from app.agent.context.budget import ContextMessageBudgeter
from app.agent.context.formatter import ConversationContextFormatter
from app.agent.context.tools import ToolExecutor
from app.agent.context.tools.registry import ToolRegistry
from app.services.llm import ChatModel


@dataclass(frozen=True)
class LLMProvider:
    """统一提供图内使用的基础模型。"""

    # 图内默认使用的基础聊天模型实例。
    base_model: ChatModel

    def model(self) -> ChatModel:
        # 返回基础模型，供各节点按需直接用或 bind_tools 后再用。
        return self.base_model


@dataclass(frozen=True)
class GraphRuntimeContext:
    """LangGraph 节点共享的运行时依赖。"""

    # 统一模型提供器。
    llm_provider: LLMProvider
    # 上下文构建器，负责初始 bundle 和工具结果回写。
    context_builder: ConversationContextBuilder
    # 上下文格式化器，负责把 bundle 变成模型消息。
    context_formatter: ConversationContextFormatter
    # 消息预算裁剪器，负责控制 token 开销。
    context_budgeter: ContextMessageBudgeter
    # 工具注册中心，负责提供工具类别、工具规格和工具对象。
    tool_registry: ToolRegistry
    # 工具执行器，负责真正执行 tool_call。
    tool_executor: ToolExecutor
