from __future__ import annotations

from app.agent.graph.main_graph.runtime import GraphRuntimeContext
from app.memory.models import RetrievedMemoryHit

from ..state import ReplyState


def rerank_memory_node(state: ReplyState, context: GraphRuntimeContext) -> dict[str, object]:
    del context
    reranked_memory_hits = _select_top_memory_hits(state.retrieved_memory_hits)
    return {"reranked_memory_hits": reranked_memory_hits}


def _select_top_memory_hits(retrieved_memory_hits: tuple[RetrievedMemoryHit, ...]) -> tuple[RetrievedMemoryHit, ...]:
    return tuple(
        sorted(
            retrieved_memory_hits,
            key=lambda hit: (-hit.score, -hit.record.message_time.timestamp(), hit.record.message_id),
        )[:3]
    )
