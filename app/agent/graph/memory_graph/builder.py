from __future__ import annotations

"""长期记忆处理图的构建入口。

这个文件只负责把各个节点按固定顺序装配成一张 LangGraph，
不承载节点内部业务逻辑。
"""

from langgraph.graph import END, START, StateGraph

from app.agent.graph.main_graph.runtime import LLMProvider

from app.agent.graph.memory_graph.nodes.extract_memory import extract_memory_node
from app.agent.graph.memory_graph.nodes.load_conversation import load_conversation_node
from app.agent.graph.memory_graph.nodes.merge_memory import merge_memory_node
from app.agent.graph.memory_graph.nodes.save_memory import save_memory_node
from app.agent.graph.memory_graph.nodes.score_importance import score_importance_node

from app.agent.graph.memory_graph.runtime import MemoryGraphRuntimeContext, MemoryGraphServices
from app.agent.graph.memory_graph.state import MemoryGraphState


def build_memory_graph(llm_provider: LLMProvider, services: MemoryGraphServices):
    """基于共享依赖装配长期记忆处理图。

    图的执行顺序固定为：
    1. 读取本轮需要处理的新对话。
    2. 提取长期记忆候选。
    3. 过滤重要候选。
    4. 合并长期记忆摘要与用户画像 patch。
    5. 持久化最终结果。
    """

    graph = StateGraph(MemoryGraphState)
    runtime_context = MemoryGraphRuntimeContext(
        llm_provider=llm_provider,
        services=services,
    )

    def load_conversation_graph_node(state: MemoryGraphState) -> dict[str, object]:
        """包装读取对话节点，适配 LangGraph 调用签名。"""

        return load_conversation_node(state=state, context=runtime_context)

    def extract_memory_graph_node(state: MemoryGraphState) -> dict[str, object]:
        """包装候选提取节点，适配 LangGraph 调用签名。"""

        return extract_memory_node(state=state, context=runtime_context)

    def score_importance_graph_node(state: MemoryGraphState) -> dict[str, object]:
        """包装重要度过滤节点，适配 LangGraph 调用签名。"""

        return score_importance_node(state=state, context=runtime_context)

    def merge_memory_graph_node(state: MemoryGraphState) -> dict[str, object]:
        """包装长期记忆合并节点，适配 LangGraph 调用签名。"""

        return merge_memory_node(state=state, context=runtime_context)

    def save_memory_graph_node(state: MemoryGraphState) -> dict[str, object]:
        """包装持久化节点，适配 LangGraph 调用签名。"""

        return save_memory_node(state=state, context=runtime_context)

    graph.add_node("load_conversation", load_conversation_graph_node)
    graph.add_node("extract_memory", extract_memory_graph_node)
    graph.add_node("score_importance", score_importance_graph_node)
    graph.add_node("merge_memory", merge_memory_graph_node)
    graph.add_node("save_memory", save_memory_graph_node)

    graph.add_edge(START, "load_conversation")
    graph.add_edge("load_conversation", "extract_memory")
    graph.add_edge("extract_memory", "score_importance")
    graph.add_edge("score_importance", "merge_memory")
    graph.add_edge("merge_memory", "save_memory")
    graph.add_edge("save_memory", END)
    return graph.compile()
