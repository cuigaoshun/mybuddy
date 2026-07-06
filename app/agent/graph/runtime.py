from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from app.agent.context.builder import ConversationContextBuilder
from app.agent.context.budget import ContextMessageBudgeter
from app.agent.context.formatter import ConversationContextFormatter
from app.agent.context.tools import ToolExecutor
from app.agent.graph.state import ReplyState
from app.services.llm import ChatModel


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
    context_builder: ConversationContextBuilder
    context_formatter: ConversationContextFormatter
    context_budgeter: ContextMessageBudgeter
    tool_executor: ToolExecutor
    selector_model_resolver: Callable[[ReplyState, "GraphRuntimeContext"], ChatModel]
    reply_model_resolver: Callable[[ReplyState, "GraphRuntimeContext"], tuple[ChatModel, str]]
