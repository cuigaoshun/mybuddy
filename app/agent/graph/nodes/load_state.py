from __future__ import annotations

from app.agent.graph.runtime import GraphRuntimeContext

from ..state import ReplyState


def load_state_node(state: ReplyState, context: GraphRuntimeContext) -> ReplyState:
    del context
    thread_id = f"{state.message.im_type}:{state.message.chat_id}:{state.message.sender_id}"
    return state.model_copy(update={"thread_id": thread_id, "canonical_query": state.message.text.strip()})
