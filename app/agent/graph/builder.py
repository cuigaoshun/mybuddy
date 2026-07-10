from __future__ import annotations

from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime

from app.agent.context.budget import ContextMessageBudgeter
from app.agent.context.formatter import ConversationContextFormatter
from app.agent.context.tools.history_tools.search_history import HistoryToolDefinition
from app.agent.context.tools.models import RegisteredTool
from app.agent.context.tools.registry import ToolRegistry
from app.agent.context.tools.web_search_tools.search_web import WebSearchToolDefinition
from app.agent.graph.runtime import GraphRuntimeContext, GraphServices, LLMProvider

from .constants import GraphNodes
from .nodes.assemble_context import assemble_context_node
from .nodes.chat_model import chat_model_node
from .nodes.load_recent import load_recent_node
from .nodes.rerank_memory import rerank_memory_node
from .nodes.retrieve_memory import retrieve_memory_node
from .nodes.tool_executor import execute_tools_node

from .routes import route_after_chat_model
from .state import ReplyState


def build_graph(
    llm_provider: LLMProvider,
    service: GraphServices,
):
    """构建按新工具链路组织的 LangGraph 主流程。"""

    # 在图外先准备好上下文构建、格式化和预算裁剪组件。
    registered_tools = _build_tools(service)
    # 创建上下文格式化器，负责把 ContextBundle 转成模型真正消费的消息序列。
    context_formatter = ConversationContextFormatter()
    # 创建消息预算裁剪器，后续如果恢复裁剪逻辑可直接复用。
    context_budgeter = ContextMessageBudgeter(llm_provider.model())
    # 基于已注册工具构造统一 registry，避免节点层重复拼工具集合。
    tool_registry = ToolRegistry(registered_tools)
    # 把所有节点共享依赖统一收敛到运行时上下文里，避免节点层重复装配。
    runtime_context = GraphRuntimeContext(
        llm_provider=llm_provider,
        services=service,
        context_formatter=context_formatter,
        context_budgeter=context_budgeter,
        tool_registry=tool_registry,
    )

    # 下面这些局部包装函数只负责把运行时上下文闭包进具体 node 调用里。
    def load_recent_graph_node(state: ReplyState) -> ReplyState:
        return load_recent_node(state=state, context=runtime_context)

    def retrieve_memory_graph_node(state: ReplyState) -> ReplyState:
        return retrieve_memory_node(state=state, context=runtime_context)

    def rerank_memory_graph_node(state: ReplyState) -> ReplyState:
        return rerank_memory_node(state=state, context=runtime_context)

    def assemble_context_graph_node(state: ReplyState) -> ReplyState:
        return assemble_context_node(state=state, context=runtime_context)

    def chat_model_graph_node(state: ReplyState) -> ReplyState:
        return chat_model_node(state=state, context=runtime_context)

    def execute_tools_graph_node(
        state: ReplyState,
        runtime: Runtime,
    ) -> ReplyState:
        return execute_tools_node(state=state, context=runtime_context, runtime=runtime)

    # 创建以 ReplyState 为统一状态结构的 LangGraph。
    graph = StateGraph(ReplyState)
    # 注册最近对话加载节点，负责准备当前轮最近连续消息。
    graph.add_node(GraphNodes.LOAD_RECENT.value, load_recent_graph_node)
    # 注册记忆召回节点，负责从长期记忆里拉取原始命中结果。
    graph.add_node(GraphNodes.RETRIEVE_MEMORY.value, retrieve_memory_graph_node)
    # 注册记忆重排节点，负责把原始命中裁成当前轮要保留的少量候选。
    graph.add_node(GraphNodes.RERANK_MEMORY.value, rerank_memory_graph_node)
    # 注册上下文组装节点，负责把 recent 和记忆证据拼成最终 ContextBundle。
    graph.add_node(GraphNodes.ASSEMBLE_CONTEXT.value, assemble_context_graph_node)
    # 注册主模型调用节点。
    graph.add_node(GraphNodes.CHAT_MODEL.value, chat_model_graph_node)
    # 注册统一工具执行节点。
    graph.add_node(GraphNodes.EXECUTE_TOOLS.value, execute_tools_graph_node)
    # 图开始后先并行读取最近消息。
    graph.add_edge(START, GraphNodes.LOAD_RECENT.value)
    # 图开始后同时并行发起长期记忆召回。
    graph.add_edge(START, GraphNodes.RETRIEVE_MEMORY.value)
    # 长期记忆召回完成后，继续进入重排节点筛掉低优先级命中。
    graph.add_edge(GraphNodes.RETRIEVE_MEMORY.value, GraphNodes.RERANK_MEMORY.value)
    # 等最近消息与重排后的长期记忆都就绪后，再统一组装上下文。
    graph.add_edge([GraphNodes.LOAD_RECENT.value, GraphNodes.RERANK_MEMORY.value], GraphNodes.ASSEMBLE_CONTEXT.value)
    # 上下文组装完成后再进入主模型推理。
    graph.add_edge(GraphNodes.ASSEMBLE_CONTEXT.value, GraphNodes.CHAT_MODEL.value)
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


def _build_tools(
    service: GraphServices,
) -> tuple[RegisteredTool, ...]:
    # 当前图装配阶段先把核心历史工具与网页搜索工具都注册进去。
    return (
        HistoryToolDefinition.build(service.conversation_memory_service),
        WebSearchToolDefinition.build(service.web_search_service),
    )
