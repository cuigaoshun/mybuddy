from __future__ import annotations

from app.agent.graph.runtime import GraphRuntimeContext

from ..state import ReplyState


def load_recent_node(state: ReplyState, context: GraphRuntimeContext) -> dict[str, object]:
    """读取当前会话最近连续对话，并写回图状态。"""

    return {
        # 最近对话只排除当前这条正在处理的消息，避免重复回灌。
        "recent_records": tuple(
            # 统一通过运行时聚合服务读取最近消息，保持节点层不直接依赖底层仓储。
            context.services.conversation_memory_service.list_recent_messages(
                user_id=state.message.sender_id,
                im_type=state.message.im_type,
                chat_id=state.message.chat_id,
                exclude_message_id=state.message.message_id,
            )
        ),
    }
