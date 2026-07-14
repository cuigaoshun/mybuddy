from __future__ import annotations

"""候选长期记忆重要度过滤节点。

当前版本仍然保持最简单的阈值过滤策略，
把 extract 阶段产出的候选记忆按 importance 截断。
"""

from app.agent.graph.memory_graph.runtime import MemoryGraphRuntimeContext
from app.agent.graph.memory_graph.state import MemoryGraphState


def score_importance_node(state: MemoryGraphState, context: MemoryGraphRuntimeContext) -> dict[str, object]:
    """按重要度阈值保留候选长期记忆。"""

    del context
    important_candidates = tuple(candidate for candidate in state.extracted_candidates if candidate.importance >= 0.5)
    return {"important_candidates": important_candidates}
