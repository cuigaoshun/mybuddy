from __future__ import annotations

from app.agent.graph.runtime import GraphRuntimeContext
from app.memory.models import RetrievedMemoryHit

from ..state import ReplyState


def rerank_memory_node(state: ReplyState, context: GraphRuntimeContext) -> dict[str, object]:
    """对长期记忆命中结果做轻量重排，并只保留当前轮最重要的候选。"""

    # 当前阶段先用简单排序策略：按 score 倒序取前三。
    reranked_memory_hits = _select_top_memory_hits(state.retrieved_memory_hits)
    return {
        # 把重排后的候选写回状态，供后续 assemble_context 节点消费。
        "reranked_memory_hits": reranked_memory_hits,
    }


def _select_top_memory_hits(
    retrieved_memory_hits: tuple[RetrievedMemoryHit, ...],
) -> tuple[RetrievedMemoryHit, ...]:
    """按相关分数和时间稳定排序，截断出 top 3 记忆候选。"""

    return tuple(
        sorted(
            # 先按 score 倒序，再按消息时间和消息 ID 保证结果稳定。
            retrieved_memory_hits,
            key=lambda hit: (-hit.score, -hit.record.message_time.timestamp(), hit.record.message_id),
        )[:3]
    )
