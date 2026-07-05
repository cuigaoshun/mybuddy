from __future__ import annotations

from langchain_core.messages import AIMessage, ToolMessage

from app.agent.context.builder import ConversationContextBuilder
from app.agent.context.tools import ToolExecutor
from app.agent.context.tools.models import ToolCallContext

from ...state import ReplyState


def tool_node(
    state: ReplyState,
    tool_executor: ToolExecutor,
    context_builder: ConversationContextBuilder,
) -> ReplyState:
    """工具执行节点：执行模型选中的小工具并把结果回灌到上下文。"""

    last_message = state.messages[-1]
    if not isinstance(last_message, AIMessage):
        return state

    # 工具查询只负责补充上下文证据，不直接重写主时间线消息。
    updated_messages = list(state.messages)
    next_bundle = state.context_bundle
    # 当前工具执行上下文限定在本次会话内，避免跨会话误检索。
    call_context = ToolCallContext(
        user_id=state.message.sender_id,
        im_type=state.message.im_type,
        chat_id=state.message.chat_id,
    )
    for tool_call in last_message.tool_calls:
        tool_call_id = tool_call.get("id")
        if not isinstance(tool_call_id, str) or not tool_call_id:
            continue
        tool_name = tool_call.get("name")
        if not isinstance(tool_name, str) or not tool_name:
            continue
        tool_args = tool_call.get("args")
        # 先由模型决定小工具，再由执行器路由到对应实现。
        execution_result = tool_executor.execute(
            tool_name=tool_name,
            tool_args=tool_args,
            call_context=call_context,
            tool_call_id=tool_call_id,
        )
        if execution_result is None:
            continue
        # 工具的结构化结果进入上下文包，供下一轮模型继续使用。
        next_bundle = context_builder.append_tool_results(next_bundle, execution_result.structured_results)
        next_bundle = context_builder.append_tool_context(
            next_bundle,
            tool_name=execution_result.tool_name,
            content_text=execution_result.text,
        )
        # 同时把工具结果作为 ToolMessage 追加到消息序列里，维持 LangGraph 工具回环格式。
        updated_messages.append(
            ToolMessage(
                content=execution_result.text,
                tool_call_id=execution_result.tool_call_id,
            )
        )

    return state.model_copy(
        update={
            "messages": tuple(updated_messages),
            "context_bundle": next_bundle,
            "refresh_after_tool": state.refresh_after_tool,
        }
    )
