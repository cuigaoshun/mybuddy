from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from app.agent.context.builder import ConversationContextBuilder
from app.agent.context.budget import ContextMessageBudgeter
from app.agent.context.formatter import ConversationContextFormatter
from app.agent.context.tools import ToolExecutor
from app.memory.service import ConversationMemoryService
from app.services.llm import ChatModel

from .nodes.input import input_node
from .nodes.reply import reply_node
from .nodes.selector import select_category_node
from .nodes.tool import tool_node
from .routes import route_after_reply, route_after_select_category
from .state import ReplyState


def build_graph(chat_model: ChatModel, conversation_memory_service: ConversationMemoryService):
    """构建一期陪伴型 Agent 使用的 LangGraph 主流程。"""

    # 在图外先准备好上下文构建、格式化和预算裁剪组件。
    context_builder = ConversationContextBuilder(conversation_memory_service)
    context_formatter = ConversationContextFormatter()
    context_budgeter = ContextMessageBudgeter(chat_model)
    # 工具执行器负责把模型选择的小工具真正映射到仓库内部实现。
    tool_executor = ToolExecutor(context_builder.get_tool_registry())
    # 第一阶段只给模型一个“工具大类选择器”，避免一开始暴露全量小工具 schema。
    category_selector_tool = context_builder.build_category_selector_tool()
    category_selector_model = chat_model.bind_tools([category_selector_tool])

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
    # 工具分类节点：先决定是否需要工具以及应该使用哪个大类。
    graph.add_node(
        "select_category",
        lambda state: select_category_node(
            state=state,
            category_selector_model=category_selector_model,
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
    # 整体流程：START -> input -> select_category -> reply -> (tool -> reply)* -> END。
    graph.add_edge(START, "input")
    graph.add_edge("input", "select_category")
    graph.add_conditional_edges("select_category", route_after_select_category, {"reply": "reply"})
    graph.add_conditional_edges("reply", route_after_reply, {"tool": "tool", "end": END})
    graph.add_edge("tool", "reply")
    return graph.compile()
