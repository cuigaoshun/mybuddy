from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from app.agent.context.builder import ConversationContextBuilder
from app.agent.context.budget import ContextMessageBudgeter
from app.agent.context.formatter import ConversationContextFormatter
from app.agent.context.tools import ToolExecutor
from app.agent.graph.runtime import GraphRuntimeContext, LLMProvider
from app.memory.service import ConversationMemoryService
from app.services.web_search import ExaWebSearchService

from .nodes.chat_model import chat_model_node
from .nodes.context_update import context_update_node
from .nodes.decision import decision_node
from .nodes.load_memory import load_memory_node
from .nodes.load_state import load_state_node
from .nodes.rewrite import rewrite_node
from .nodes.tool_executor import tool_executor_node
from .nodes.tool_expansion import tool_expansion_node
from .nodes.tool_selector import tool_selector_node

from .routes import route_after_decision, route_after_tool_selector
from .state import ReplyState


def build_graph(
    llm_provider: LLMProvider,
    conversation_memory_service: ConversationMemoryService,
    web_search_service: ExaWebSearchService,
):
    """构建按新链路组织的 LangGraph 主流程。"""

    # 在图外先准备好上下文构建、格式化和预算裁剪组件。
    context_builder = ConversationContextBuilder(conversation_memory_service, web_search_service)
    context_formatter = ConversationContextFormatter()
    context_budgeter = ContextMessageBudgeter(llm_provider.model())
    tool_registry = context_builder.get_tool_registry()
    tool_executor = ToolExecutor(tool_registry)
    runtime_context = GraphRuntimeContext(
        llm_provider=llm_provider,
        context_builder=context_builder,
        context_formatter=context_formatter,
        context_budgeter=context_budgeter,
        tool_registry=tool_registry,
        tool_executor=tool_executor,
    )

    def load_state_graph_node(state: ReplyState) -> ReplyState:
        return load_state_node(state=state, context=runtime_context)

    def load_memory_graph_node(state: ReplyState) -> ReplyState:
        return load_memory_node(state=state, context=runtime_context)

    def rewrite_graph_node(state: ReplyState) -> ReplyState:
        return rewrite_node(state=state, context=runtime_context)

    def tool_selector_graph_node(state: ReplyState) -> ReplyState:
        return tool_selector_node(state=state, context=runtime_context)

    def tool_expansion_graph_node(state: ReplyState) -> ReplyState:
        return tool_expansion_node(state=state, context=runtime_context)

    def chat_model_graph_node(state: ReplyState) -> ReplyState:
        return chat_model_node(state=state, context=runtime_context)

    def decision_graph_node(state: ReplyState) -> ReplyState:
        return decision_node(state=state, context=runtime_context)

    def tool_executor_graph_node(state: ReplyState) -> ReplyState:
        return tool_executor_node(state=state, context=runtime_context)

    def context_update_graph_node(state: ReplyState) -> ReplyState:
        return context_update_node(state=state, context=runtime_context)

    graph = StateGraph(ReplyState)
    graph.add_node("load_state", load_state_graph_node)
    graph.add_node("load_memory", load_memory_graph_node)
    graph.add_node("rewrite", rewrite_graph_node)
    graph.add_node("tool_selector", tool_selector_graph_node)
    graph.add_node("tool_expansion", tool_expansion_graph_node)
    graph.add_node("chat_model", chat_model_graph_node)
    graph.add_node("decision", decision_graph_node)
    graph.add_node("tool_executor", tool_executor_graph_node)
    graph.add_node("context_update", context_update_graph_node)
    graph.add_edge(START, "load_state")
    graph.add_edge("load_state", "load_memory")
    graph.add_edge("load_memory", "rewrite")
    graph.add_edge("rewrite", "tool_selector")
    graph.add_conditional_edges("tool_selector", route_after_tool_selector, {"tool_expansion": "tool_expansion", "tool_executor": "tool_executor", "end": END})
    graph.add_edge("tool_expansion", "chat_model")
    graph.add_edge("chat_model", "decision")
    graph.add_edge("tool_executor", "context_update")
    graph.add_edge("context_update", "decision")
    graph.add_conditional_edges("decision", route_after_decision, {"tool_selector": "tool_selector", "tool_executor": "tool_executor", "end": END})
    return graph.compile()
