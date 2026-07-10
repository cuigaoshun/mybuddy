from __future__ import annotations

from app.agent.graph.runtime import GraphRuntimeContext

from ..state import ReplyState


def load_recent_node(state: ReplyState, context: GraphRuntimeContext) -> ReplyState:
    return state.model_copy(
        update={
            "recent_records": tuple(
                context.services.conversation_memory_service.list_recent_messages(
                    user_id=state.message.sender_id,
                    im_type=state.message.im_type,
                    chat_id=state.message.chat_id,
                    exclude_message_id=state.message.message_id,
                )
            ),
        }
    )
