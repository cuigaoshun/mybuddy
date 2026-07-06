from __future__ import annotations

from app.agent.graph.runtime import GraphRuntimeContext
from app.agent.util import extract_reply_text

from ..helpers import build_chat_messages, invoke_model
from ..state import ReplyState


def chat_model_node(state: ReplyState, context: GraphRuntimeContext) -> ReplyState:
    messages = build_chat_messages(state, context)
    if state.active_tool_specs:
        model = context.llm_provider.model().bind_tools([tool_spec.tool for tool_spec in state.active_tool_specs])
        bound_tool_names = state.active_tool_names
    else:
        model = context.llm_provider.model()
        bound_tool_names = ()
    reply = invoke_model(model=model, messages=messages, bound_tool_names=bound_tool_names)
    updated_messages = tuple([*messages, reply])
    final_reply = None if getattr(reply, "tool_calls", None) else extract_reply_text(reply)
    return state.model_copy(
        update={
            "messages": updated_messages,
            "final_reply": final_reply,
            "decision_source": "after_chat_model",
        }
    )
