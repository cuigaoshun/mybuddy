from __future__ import annotations

from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime

from app.agent.context.budget import ContextMessageBudgeter
from app.agent.context.main_graph.formatter import ConversationContextFormatter
from app.agent.context.tool import ContextTool
from app.agent.context.tools.history_tools.search_history import HistoryToolDefinition
from app.agent.context.tools.models import RegisteredTool
from app.agent.context.tools.registry import ToolRegistry
from app.agent.context.tools.web_search_tools.search_web import WebSearchToolDefinition
from app.agent.graph.main_graph.runtime import GraphRuntimeContext, GraphServices, LLMProvider

from .constants import GraphNodes
from .nodes.assemble_context import assemble_context_node
from .nodes.chat_model import chat_model_node
from .nodes.load_recent import load_recent_node
from .nodes.rerank_memory import rerank_memory_node
from .nodes.retrieve_memory import retrieve_memory_node
from .nodes.tool_executor import execute_tools_node
from .routes import route_after_chat_model
from .state import ReplyState


def build_graph(llm_provider: LLMProvider, service: GraphServices):
    registered_tools = _build_tools(service)
    context_formatter = ConversationContextFormatter()
    context_budgeter = ContextMessageBudgeter(llm_provider.model())
    context_tool = ContextTool(formatter=context_formatter, budgeter=context_budgeter)
    tool_registry = ToolRegistry(registered_tools)
    runtime_context = GraphRuntimeContext(
        llm_provider=llm_provider,
        services=service,
        context_tool=context_tool,
        tool_registry=tool_registry,
    )

    def load_recent_graph_node(state: ReplyState) -> dict[str, object]:
        return load_recent_node(state=state, context=runtime_context)

    def retrieve_memory_graph_node(state: ReplyState) -> dict[str, object]:
        return retrieve_memory_node(state=state, context=runtime_context)

    def rerank_memory_graph_node(state: ReplyState) -> dict[str, object]:
        return rerank_memory_node(state=state, context=runtime_context)

    def assemble_context_graph_node(state: ReplyState) -> dict[str, object]:
        return assemble_context_node(state=state, context=runtime_context)

    def chat_model_graph_node(state: ReplyState) -> dict[str, object]:
        return chat_model_node(state=state, context=runtime_context)

    def execute_tools_graph_node(state: ReplyState, runtime: Runtime) -> dict[str, object]:
        return execute_tools_node(state=state, context=runtime_context, runtime=runtime)

    graph = StateGraph(ReplyState)
    graph.add_node(GraphNodes.LOAD_RECENT.value, load_recent_graph_node)
    graph.add_node(GraphNodes.RETRIEVE_MEMORY.value, retrieve_memory_graph_node)
    graph.add_node(GraphNodes.RERANK_MEMORY.value, rerank_memory_graph_node)
    graph.add_node(GraphNodes.ASSEMBLE_CONTEXT.value, assemble_context_graph_node)
    graph.add_node(GraphNodes.CHAT_MODEL.value, chat_model_graph_node)
    graph.add_node(GraphNodes.EXECUTE_TOOLS.value, execute_tools_graph_node)
    graph.add_edge(START, GraphNodes.LOAD_RECENT.value)
    graph.add_edge(START, GraphNodes.RETRIEVE_MEMORY.value)
    graph.add_edge(GraphNodes.RETRIEVE_MEMORY.value, GraphNodes.RERANK_MEMORY.value)
    graph.add_edge([GraphNodes.LOAD_RECENT.value, GraphNodes.RERANK_MEMORY.value], GraphNodes.ASSEMBLE_CONTEXT.value)
    graph.add_edge(GraphNodes.ASSEMBLE_CONTEXT.value, GraphNodes.CHAT_MODEL.value)
    graph.add_conditional_edges(
        GraphNodes.CHAT_MODEL.value,
        route_after_chat_model,
        {
            GraphNodes.EXECUTE_TOOLS.value: GraphNodes.EXECUTE_TOOLS.value,
            GraphNodes.END.value: END,
        },
    )
    graph.add_edge(GraphNodes.EXECUTE_TOOLS.value, GraphNodes.CHAT_MODEL.value)
    return graph.compile()


def _build_tools(service: GraphServices) -> tuple[RegisteredTool, ...]:
    return (
        HistoryToolDefinition.build(service.conversation_memory_service),
        WebSearchToolDefinition.build(service.web_search_service),
    )
