from __future__ import annotations

"""长期记忆持久化节点。

这个节点只负责把上游已经合并完成的长期记忆快照写入存储，
不再重复参与任何摘要生成或画像合并逻辑。
"""

from app.agent.graph.memory_graph.runtime import MemoryGraphRuntimeContext
from app.agent.graph.memory_graph.state import MemoryGraphState


def save_memory_node(state: MemoryGraphState, context: MemoryGraphRuntimeContext) -> dict[str, object]:
    """把最终长期记忆快照写入用户长期记忆存储。"""

    if state.merged_user_memory is None or not state.conversation_records:
        return {"saved": False}
    context.services.user_memory_service.save_user_memory(state.merged_user_memory)
    return {"saved": True}
