from __future__ import annotations

"""读取长期记忆待处理对话节点。

这个节点负责拿到当前会话最近一次已处理消息之后的新增记录，
为后续提取长期记忆候选提供原始输入。
"""

from app.agent.graph.memory_graph.runtime import MemoryGraphRuntimeContext
from app.agent.graph.memory_graph.state import MemoryGraphState


def load_conversation_node(state: MemoryGraphState, context: MemoryGraphRuntimeContext) -> dict[str, object]:
    """读取旧长期记忆快照，并拉取本轮待处理的新消息列表。"""

    existing_user_memory = context.services.user_memory_service.get_user_memory(
        user_id=state.session.user_id,
    )
    after_message_id = existing_user_memory.last_processed_message_id if existing_user_memory is not None else None
    conversation_records = tuple(
        context.services.conversation_memory_service.list_messages_after_message_id(
            user_id=state.session.user_id,
            im_type=state.session.im_type,
            chat_id=state.session.chat_id,
            after_message_id=after_message_id,
            limit=50,
        )
    )
    return {
        "existing_user_memory": existing_user_memory,
        "conversation_records": conversation_records,
    }
