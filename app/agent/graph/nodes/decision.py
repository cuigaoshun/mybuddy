from __future__ import annotations

from langchain_core.messages import AIMessage

from app.agent.graph.runtime import GraphRuntimeContext

from ..state import ReplyState


def decision_node(state: ReplyState, context: GraphRuntimeContext) -> ReplyState:
    del context
    next_step = "end"
    if state.decision_source == "after_chat_model":
        last_message = state.messages[-1] if state.messages else None
        if isinstance(last_message, AIMessage) and getattr(last_message, "tool_calls", None):
            next_step = "tool_executor"
        elif state.final_reply is not None:
            next_step = "end"
    elif state.decision_source == "after_context_update":
        if state.tool_round >= state.max_tool_rounds:
            next_step = "end"
        else:
            next_step = "tool_selector"
    return state.model_copy(update={"next_step": next_step})
