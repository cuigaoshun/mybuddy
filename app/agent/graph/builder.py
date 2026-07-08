from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from app.agent.context.builder import ConversationContextBuilder
from app.agent.context.budget import ContextMessageBudgeter
from app.agent.context.formatter import ConversationContextFormatter
from app.agent.graph.runtime import GraphRuntimeContext, LLMProvider
from app.memory.service import ConversationMemoryService
from app.services.web_search import ExaWebSearchService

from .nodes.chat_model import chat_model_node
from .nodes.load_memory import load_memory_node
from .nodes.tool_executor import core_tools_node, dynamic_tool_node

from .routes import route_after_chat_model
from .state import ReplyState


def build_graph(
    llm_provider: LLMProvider,
    conversation_memory_service: ConversationMemoryService,
    web_search_service: ExaWebSearchService,
):
    """构建按新工具链路组织的 LangGraph 主流程。"""

    # 在图外先准备好上下文构建、格式化和预算裁剪组件。
    context_builder = ConversationContextBuilder(conversation_memory_service, web_search_service)
    context_formatter = ConversationContextFormatter()
    context_budgeter = ContextMessageBudgeter(llm_provider.model())
    tool_registry = context_builder.get_tool_registry()
    # 把所有节点共享依赖统一收敛到运行时上下文里，避免节点层重复装配。
    runtime_context = GraphRuntimeContext(
        llm_provider=llm_provider,
        context_builder=context_builder,
        context_formatter=context_formatter,
        context_budgeter=context_budgeter,
        tool_registry=tool_registry,
    )

    # 下面这些局部包装函数只负责把运行时上下文闭包进具体 node 调用里。
    def load_memory_graph_node(state: ReplyState) -> ReplyState:
        return load_memory_node(state=state, context=runtime_context)

    def chat_model_graph_node(state: ReplyState) -> ReplyState:
        return chat_model_node(state=state, context=runtime_context)

    def core_tools_graph_node(state: ReplyState) -> ReplyState:
        return core_tools_node(state=state, context=runtime_context)

    def dynamic_tool_graph_node(state: ReplyState) -> ReplyState:
        return dynamic_tool_node(state=state, context=runtime_context)

    # 创建以 ReplyState 为统一状态结构的 LangGraph。
    graph = StateGraph(ReplyState)
    # 注册记忆加载节点。
    graph.add_node("load_memory", load_memory_graph_node)
    # 注册主模型调用节点。
    graph.add_node("chat_model", chat_model_graph_node)
    # 注册核心工具执行节点。
    graph.add_node("core_tools", core_tools_graph_node)
    # 注册动态工具执行节点。
    graph.add_node("dynamic_tools", dynamic_tool_graph_node)
    # 起点先进入上下文加载。
    graph.add_edge(START, "load_memory")
    # 初始上下文准备好后直接进入主模型节点。
    graph.add_edge("load_memory", "chat_model")
    # chat_model 决定是结束、走核心工具，还是走已解锁的动态工具。
    graph.add_conditional_edges("chat_model", route_after_chat_model, {"chat_model": "chat_model", "core_tools": "core_tools", "dynamic_tools": "dynamic_tools", "end": END})
    # 核心工具执行后继续回到主模型。
    graph.add_edge("core_tools", "chat_model")
    # 动态工具执行后继续回到主模型。
    graph.add_edge("dynamic_tools", "chat_model")
    # 编译并返回可执行图实例。
    return graph.compile()
