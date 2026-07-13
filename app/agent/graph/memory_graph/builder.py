from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from app.agent.graph.memory_graph.nodes import extract_memory_node, load_conversation_node, merge_memory_node, save_memory_node, score_importance_node
from app.agent.graph.main_graph.runtime import LLMProvider

from app.agent.graph.memory_graph.runtime import MemoryGraphRuntimeContext, MemoryGraphServices
from app.agent.graph.memory_graph.state import MemoryGraphState


def build_memory_graph(llm_provider: LLMProvider, services: MemoryGraphServices):
    graph = StateGraph(MemoryGraphState)
    runtime_context = MemoryGraphRuntimeContext(
        llm_provider=llm_provider,
        services=services,
    )

    def load_conversation_graph_node(state: MemoryGraphState) -> dict[str, object]:
        return load_conversation_node(state=state, context=runtime_context)

    def extract_memory_graph_node(state: MemoryGraphState) -> dict[str, object]:
        return extract_memory_node(state=state, context=runtime_context)

    def score_importance_graph_node(state: MemoryGraphState) -> dict[str, object]:
        return score_importance_node(state=state, context=runtime_context)

    def merge_memory_graph_node(state: MemoryGraphState) -> dict[str, object]:
        return merge_memory_node(state=state, context=runtime_context)

    def save_memory_graph_node(state: MemoryGraphState) -> dict[str, object]:
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
