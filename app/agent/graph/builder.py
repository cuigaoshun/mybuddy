from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from app.agent.context.builder import ConversationContextBuilder
from app.agent.context.budget import ContextMessageBudgeter
from app.agent.context.formatter import ConversationContextFormatter
from app.agent.context.tools import ToolExecutor
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
    chat_model: ChatModel,
    conversation_memory_service: ConversationMemoryService,
    web_search_service: ExaWebSearchService,
): 
    """构建一期陪伴型 Agent 使用的 LangGraph 主流程。"""

    # 在图外先准备好上下文构建、格式化和预算裁剪组件。
    context_builder = ConversationContextBuilder(conversation_memory_service, web_search_service)
    context_formatter = ConversationContextFormatter()
    context_budgeter = ContextMessageBudgeter(chat_model)
    # 工具执行器负责把模型选择的小工具真正映射到仓库内部实现。
    tool_executor = ToolExecutor(context_builder.get_tool_registry())
    # 第一阶段同时暴露工具大类选择器和当前可直接使用的小工具。
    category_selector_tool = context_builder.build_category_selector_tool()
    tool_selector_model = chat_model.bind_tools([category_selector_tool, *context_builder.list_entry_langchain_tools()])

    graph = StateGraph(ReplyState)
    # 输入节点：把 context bundle 格式化成这一轮真正送模的 messages。
    graph.add_node(
        "input",
        lambda state: input_node(
            state=state,
            context_formatter=context_formatter,
            context_budgeter=context_budgeter,
        ),
    )
    # 刷新消息节点：基于最新上下文包重建消息，必要时进入 reply 或首阶段工具分流后的下一步。
    graph.add_node(
        "refresh_messages",
        lambda state: refresh_messages_node(
            state=state,
            context_formatter=context_formatter,
            context_budgeter=context_budgeter,
        ),
    )
    # 首阶段工具选择节点：可直接选具体工具，也可先选工具大类。
    graph.add_node(
        "select_tool",
        lambda state: select_tool_node(
            state=state,
            tool_selector_model=tool_selector_model,
            context_builder=context_builder,
        ),
    )
    # 正式回复节点：按 selected category 动态绑定小工具或直接作答。
    graph.add_node(
        "reply",
        lambda state: reply_node(
            state=state,
            chat_model=chat_model,
            context_builder=context_builder,
        ),
    )
    # 工具节点：执行工具并把结果补回上下文后回到 reply。
    graph.add_node(
        "tool",
        lambda state: tool_node(
            state=state,
            tool_executor=tool_executor,
            context_builder=context_builder,
        ),
    )
    # 整体流程：START -> input -> select_tool -> (refresh_messages|tool|reply|END)。
    graph.add_edge(START, "input")
    graph.add_edge("input", "select_tool")
    graph.add_conditional_edges("select_tool", route_after_select_tool, {"refresh_messages": "refresh_messages", "reply": "reply", "tool": "tool", "end": END})
    graph.add_conditional_edges("refresh_messages", route_after_refresh_messages, {"reply": "reply", "select_tool": "select_tool"})
    graph.add_conditional_edges("reply", route_after_reply, {"tool": "tool", "end": END})
    graph.add_conditional_edges("tool", route_after_tool, {"refresh_messages": "refresh_messages", "reply": "reply"})
    return graph.compile()
