from __future__ import annotations

from app.agent.graph.main_graph.runtime import GraphRuntimeContext

from ..state import ReplyState


def retrieve_memory_node(state: ReplyState, context: GraphRuntimeContext) -> dict[str, object]:
    return {
        "user_memory": context.services.user_memory_service.get_user_memory(
            user_id=state.message.user_id,
        ),
        "retrieved_memory_hits": tuple(
            context.services.conversation_memory_service.retrieve_memory_hits(
                user_id=state.message.user_id,
                query_text=state.message.text,
                limit=10,
                exclude_message_ids=(state.message.message_id,),
            )
        ),
    }
