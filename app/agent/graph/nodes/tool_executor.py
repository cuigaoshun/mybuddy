from __future__ import annotations

from langchain_core.messages import AIMessage, ToolMessage
from langgraph.prebuilt import ToolNode

from app.agent.context.tools.history_tools.search_history import bind_history_tool_state, reset_history_tool_state
from app.agent.graph.runtime import GraphRuntimeContext

from ..state import ReplyState


def core_tools_node(state: ReplyState, context: GraphRuntimeContext) -> ReplyState:
    tool_node = ToolNode(context.tool_registry.list_core_tools())
    result = tool_node.invoke({"messages": list(state.messages)})
    tool_messages = tuple(result.get("messages", []))
    return state.model_copy(
        update={
            "messages": tuple([*state.messages, *tool_messages]),
            "tool_round": state.tool_round + 1,
        }
    )


def dynamic_tool_node(state: ReplyState, context: GraphRuntimeContext) -> ReplyState:
    last_message = state.messages[-1] if state.messages else None
    if not isinstance(last_message, AIMessage):
        return state
    allowed_tool_names = set(context.tool_registry.list_category_tool_names(state.selected_tool_category)) if state.selected_tool_category else set()
    outputs: list[ToolMessage] = []
    state_token = bind_history_tool_state(state)
    try:
        for call in last_message.tool_calls:
            tool_name = call.get("name")
            tool_call_id = call.get("id")
            tool_args = call.get("args")
            if not isinstance(tool_name, str) or tool_name not in allowed_tool_names:
                continue
            if not isinstance(tool_call_id, str) or tool_call_id == "":
                continue
            result = context.tool_registry.get(tool_name).invoke(tool_args if isinstance(tool_args, dict) else {})
            outputs.append(ToolMessage(content=str(result), tool_call_id=tool_call_id))
    finally:
        reset_history_tool_state(state_token)
    if not outputs:
        return state
    return state.model_copy(
        update={
            "messages": tuple([*state.messages, *outputs]),
            "tool_round": state.tool_round + 1,
        }
    )
