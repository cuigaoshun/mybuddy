from __future__ import annotations

from app.agent.graph.runtime import GraphRuntimeContext

from ..state import ReplyState


def retrieve_memory_node(state: ReplyState, context: GraphRuntimeContext) -> ReplyState:
    return state.model_copy(
        update={
            "retrieved_memory_hits": tuple(
                context.services.conversation_memory_service.retrieve_memory_hits(
                    user_id=state.message.sender_id,
                    im_type=state.message.im_type,
                    chat_id=state.message.chat_id,
                    query_text=state.message.text,
                    limit=10,
                    exclude_message_ids=(state.message.message_id,),
                )
            ),
        }
    )
