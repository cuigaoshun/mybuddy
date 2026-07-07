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
from .nodes.load_memory import load_memory_node
from .nodes.load_state import load_state_node
from .nodes.rewrite import rewrite_node
from .nodes.tool_executor import tool_executor_node
from .nodes.tool_expansion import tool_expansion_node
from .nodes.tool_selector import tool_selector_node

from .routes import route_after_chat_model, route_after_context_update, route_after_tool_selector
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
    # 把所有节点共享依赖统一收敛到运行时上下文里，避免节点层重复装配。
    runtime_context = GraphRuntimeContext(
        llm_provider=llm_provider,
        context_builder=context_builder,
        context_formatter=context_formatter,
        context_budgeter=context_budgeter,
        tool_registry=tool_registry,
        tool_executor=tool_executor,
    )

    # 下面这些局部包装函数只负责把运行时上下文闭包进具体 node 调用里。
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

    def tool_executor_graph_node(state: ReplyState) -> ReplyState:
        return tool_executor_node(state=state, context=runtime_context)

    def context_update_graph_node(state: ReplyState) -> ReplyState:
        return context_update_node(state=state, context=runtime_context)

    # 创建以 ReplyState 为统一状态结构的 LangGraph。
    graph = StateGraph(ReplyState)
    # 注册状态初始化节点。
    graph.add_node("load_state", load_state_graph_node)
    # 注册记忆加载节点。
    graph.add_node("load_memory", load_memory_graph_node)
    # 注册查询规范化节点。
    graph.add_node("rewrite", rewrite_graph_node)
    # 注册工具选择节点。
    graph.add_node("tool_selector", tool_selector_graph_node)
    # 注册工具展开节点。
    graph.add_node("tool_expansion", tool_expansion_graph_node)
    # 注册主模型调用节点。
    graph.add_node("chat_model", chat_model_graph_node)
    # 注册工具执行节点。
    graph.add_node("tool_executor", tool_executor_graph_node)
    # 注册工具结果回写上下文节点。
    graph.add_node("context_update", context_update_graph_node)
    # 起点先进入基础状态初始化。
    graph.add_edge(START, "load_state")
    # 初始化后加载上下文记忆。
    graph.add_edge("load_state", "load_memory")
    # 记忆加载后进入 rewrite 阶段。
    graph.add_edge("load_memory", "rewrite")
    # rewrite 完成后进入工具选择。
    graph.add_edge("rewrite", "tool_selector")
    # tool_selector 负责决定结束、直接执行核心工具，还是进入工具展开。
    graph.add_conditional_edges("tool_selector", route_after_tool_selector, {"tool_expansion": "tool_expansion", "tool_executor": "tool_executor", "end": END})
    # 工具展开完成后进入主模型调用。
    graph.add_edge("tool_expansion", "chat_model")
    # 主模型调用后根据是否产生 tool_calls 决定执行工具还是结束。
    graph.add_conditional_edges("chat_model", route_after_chat_model, {"tool_executor": "tool_executor", "end": END})
    # 工具执行后把结果回写进上下文。
    graph.add_edge("tool_executor", "context_update")
    # 上下文回写后根据工具轮次决定继续循环还是结束。
    graph.add_conditional_edges("context_update", route_after_context_update, {"tool_selector": "tool_selector", "end": END})
    # 编译并返回可执行图实例。
    return graph.compile()
