from __future__ import annotations

from app.agent.graph.runtime import GraphRuntimeContext
from app.agent.util import extract_reply_text

from ..helpers import build_chat_messages, invoke_model
from ..state import ReplyState


def chat_model_node(state: ReplyState, context: GraphRuntimeContext) -> ReplyState:
    messages = build_chat_messages(state, context)
    if state.tool_round >= state.max_tool_rounds:
        model = context.llm_provider.model()
    elif state.selected_tool_category is None:
        model = context.llm_provider.model().bind_tools(context.tool_registry.list_core_tools())
    else:
        model = context.llm_provider.model().bind_tools(context.tool_registry.list_category_tools(state.selected_tool_category))
    reply = invoke_model(model=model, messages=messages)
    updated_messages = tuple([*messages, reply])
    final_reply = None if getattr(reply, "tool_calls", None) else extract_reply_text(reply)
    return state.model_copy(
        update={
            "messages": updated_messages,
            "final_reply": final_reply,
        }
    )
