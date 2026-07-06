from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from app.agent.context.builder import ConversationContextBuilder
from app.agent.context.budget import ContextMessageBudgeter
from app.agent.context.formatter import ConversationContextFormatter
from app.agent.context.tools import ToolExecutor
from app.agent.graph.runtime import GraphRuntimeContext, LLMProvider
from app.memory.service import ConversationMemoryService
from app.services.llm import ChatModel
from app.services.web_search import ExaWebSearchService

from .nodes.input import input_node, refresh_messages_node
from .nodes.reply import reply_node
from .nodes.selector import select_tool_node
from .nodes.tool import tool_node
from .routes import route_after_refresh_messages, route_after_reply, route_after_select_tool, route_after_tool
from .state import ReplyState


def build_graph(
    llm_provider: LLMProvider,
    conversation_memory_service: ConversationMemoryService,
    web_search_service: ExaWebSearchService,
):
    """构建一期陪伴型 Agent 使用的 LangGraph 主流程。"""

    # 在图外先准备好上下文构建、格式化和预算裁剪组件。
    context_builder = ConversationContextBuilder(conversation_memory_service, web_search_service)
    context_formatter = ConversationContextFormatter()
    context_budgeter = ContextMessageBudgeter(llm_provider.model())
    # 工具执行器负责把模型选择的小工具真正映射到仓库内部实现。
    tool_executor = ToolExecutor(context_builder.get_tool_registry())
    runtime_context = GraphRuntimeContext(
        llm_provider=llm_provider,
        context_builder=context_builder,
        context_formatter=context_formatter,
        context_budgeter=context_budgeter,
        tool_executor=tool_executor,
        selector_model_resolver=_build_selector_model,
        reply_model_resolver=_build_reply_model,
    )

    def input_graph_node(state: ReplyState) -> ReplyState:
        return input_node(state=state, context=runtime_context)

    def refresh_messages_graph_node(state: ReplyState) -> ReplyState:
        return refresh_messages_node(state=state, context=runtime_context)

    def select_tool_graph_node(state: ReplyState) -> ReplyState:
        return select_tool_node(state=state, context=runtime_context)

    def reply_graph_node(state: ReplyState) -> ReplyState:
        return reply_node(state=state, context=runtime_context)

    def tool_graph_node(state: ReplyState) -> ReplyState:
        return tool_node(state=state, context=runtime_context)

    graph = StateGraph(ReplyState)
    # 输入节点：把 context bundle 格式化成这一轮真正送模的 messages。
    graph.add_node("input", input_graph_node)
    # 刷新消息节点：基于最新上下文包重建消息，必要时进入 reply 或首阶段工具分流后的下一步。
    graph.add_node("refresh_messages", refresh_messages_graph_node)
    # 首阶段工具选择节点：可直接选具体工具，也可先选工具大类。
    graph.add_node("select_tool", select_tool_graph_node)
    # 正式回复节点：按 selected category 动态绑定小工具或直接作答。
    graph.add_node("reply", reply_graph_node)
    # 工具节点：执行工具并把结果补回上下文后回到 reply。
    graph.add_node("tool", tool_graph_node)
    # 整体流程：START -> input -> select_tool -> (refresh_messages|tool|reply|END)。
    graph.add_edge(START, "input")
    graph.add_edge("input", "select_tool")
    graph.add_conditional_edges("select_tool", route_after_select_tool, {"refresh_messages": "refresh_messages", "reply": "reply", "tool": "tool", "end": END})
    graph.add_conditional_edges("refresh_messages", route_after_refresh_messages, {"reply": "reply", "select_tool": "select_tool"})
    graph.add_conditional_edges("reply", route_after_reply, {"tool": "tool", "end": END})
    graph.add_conditional_edges("tool", route_after_tool, {"refresh_messages": "refresh_messages", "reply": "reply"})
    return graph.compile()


def _build_selector_model(state: ReplyState, context: GraphRuntimeContext) -> ChatModel:
    category_selector_tool = context.context_builder.build_category_selector_tool()
    entry_tools = context.context_builder.list_entry_langchain_tools()
    return context.llm_provider.model().bind_tools([category_selector_tool, *entry_tools])


def _build_reply_model(state: ReplyState, context: GraphRuntimeContext) -> tuple[ChatModel, str]:
    if state.selected_tool_category is None:
        return context.llm_provider.model(), "[]"
    tool_specs = state.context_bundle.enabled_tool_specs
    bound_tools_summary = f"{state.selected_tool_category}: {[tool_spec.name for tool_spec in tool_specs]}"
    category_tools = context.context_builder.list_langchain_tools_by_category(state.selected_tool_category)
    return context.llm_provider.model().bind_tools(category_tools), bound_tools_summary
