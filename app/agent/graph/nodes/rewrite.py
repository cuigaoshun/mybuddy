from __future__ import annotations

from app.agent.graph.runtime import GraphRuntimeContext

from ..state import ReplyState


def rewrite_node(state: ReplyState, context: GraphRuntimeContext) -> ReplyState:
    del context
    canonical_query = state.message.text.strip()
    rewrite_notes: tuple[str, ...] = ()
    if canonical_query == "":
        canonical_query = state.message.text
    return state.model_copy(update={"canonical_query": canonical_query, "rewrite_notes": rewrite_notes})
