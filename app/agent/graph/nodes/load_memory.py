from __future__ import annotations

from app.agent.graph.runtime import GraphRuntimeContext

from ..state import ReplyState


def load_memory_node(state: ReplyState, context: GraphRuntimeContext) -> ReplyState:
    context_bundle = context.context_builder.build_initial_bundle(state.message, state.session_info)
    return state.model_copy(update={"context_bundle": context_bundle})
