from __future__ import annotations

from langchain_core.messages import AIMessage, ToolMessage

from app.agent.context.tools.models import ToolCallContext, ToolExecutionResult
from app.agent.graph.runtime import GraphRuntimeContext

from ..state import ReplyState


def tool_executor_node(state: ReplyState, context: GraphRuntimeContext) -> ReplyState:
    last_message = state.messages[-1] if state.messages else None
    if not isinstance(last_message, AIMessage):
        return state.model_copy(update={"latest_tool_results": ()})

    updated_messages = list(state.messages)
    latest_tool_results: list[ToolExecutionResult] = []
    call_context = ToolCallContext(
        user_id=state.message.sender_id,
        im_type=state.message.im_type,
        chat_id=state.message.chat_id,
    )
    for tool_call in last_message.tool_calls:
        tool_call_id = tool_call.get("id")
        tool_name = tool_call.get("name")
        tool_args = tool_call.get("args")
        if not isinstance(tool_call_id, str) or not tool_call_id:
            continue
        if not isinstance(tool_name, str) or not tool_name:
            continue
        execution_result = context.tool_executor.execute(
            tool_name=tool_name,
            tool_args=tool_args,
            call_context=call_context,
            tool_call_id=tool_call_id,
        )
        if execution_result is None:
            continue
        latest_tool_results.append(execution_result)
        updated_messages.append(
            ToolMessage(
                content=execution_result.text,
                tool_call_id=execution_result.tool_call_id,
            )
        )

    cumulative_tool_results = tuple([*state.tool_results, *latest_tool_results])
    return state.model_copy(
        update={
            "messages": tuple(updated_messages),
            "latest_tool_results": tuple(latest_tool_results),
            "tool_results": cumulative_tool_results,
        }
    )
