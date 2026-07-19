from __future__ import annotations

from app.agent.graph.main_graph.runtime import GraphRuntimeContext

from ..state import ReplyState


def load_recent_node(state: ReplyState, context: GraphRuntimeContext) -> dict[str, object]:
    return {
        "recent_records": tuple(
            context.services.conversation_memory_service.list_recent_messages(
                user_id=state.message.user_id,
                chat_id=state.message.chat_id,
                exclude_message_id=state.message.message_id,
            )
        ),
    }
