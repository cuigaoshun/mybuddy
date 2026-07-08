from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from app.agent.context.builder import ConversationContextBuilder
from app.agent.context.budget import ContextMessageBudgeter
from app.agent.context.formatter import ConversationContextFormatter
from app.agent.graph.runtime import GraphRuntimeContext, LLMProvider
from app.memory.service import ConversationMemoryService
from app.services.web_search import ExaWebSearchService

from .constants import GraphNodes
from .nodes.chat_model import chat_model_node
from .nodes.load_memory import load_memory_node
from .nodes.tool_executor import execute_tools_node

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

    def execute_tools_graph_node(state: ReplyState) -> ReplyState:
        return execute_tools_node(state=state, context=runtime_context)

    # 创建以 ReplyState 为统一状态结构的 LangGraph。
    graph = StateGraph(ReplyState)
    # 注册记忆加载节点。
    graph.add_node(GraphNodes.LOAD_MEMORY.value, load_memory_graph_node)
    # 注册主模型调用节点。
    graph.add_node(GraphNodes.CHAT_MODEL.value, chat_model_graph_node)
    # 注册统一工具执行节点。
    graph.add_node(GraphNodes.EXECUTE_TOOLS.value, execute_tools_graph_node)
    # 起点先进入上下文加载。
    graph.add_edge(START, GraphNodes.LOAD_MEMORY.value)
    # 初始上下文准备好后直接进入主模型节点。
    graph.add_edge(GraphNodes.LOAD_MEMORY.value, GraphNodes.CHAT_MODEL.value)
    # chat_model 返回 GraphNodes 枚举，再由这里统一映射到真实图节点或 LangGraph 内置 END。
    graph.add_conditional_edges(
        GraphNodes.CHAT_MODEL.value,
        route_after_chat_model,
        {
            GraphNodes.CHAT_MODEL.value: GraphNodes.CHAT_MODEL.value,
            GraphNodes.EXECUTE_TOOLS.value: GraphNodes.EXECUTE_TOOLS.value,
            GraphNodes.END.value: END,
        },
    )
    # 工具执行后统一回到主模型。
    graph.add_edge(GraphNodes.EXECUTE_TOOLS.value, GraphNodes.CHAT_MODEL.value)
    # 编译并返回可执行图实例。
    return graph.compile()
