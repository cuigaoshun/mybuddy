from __future__ import annotations

from langchain_core.messages import AIMessage, ToolMessage

from app.agent.context.tools.models import ToolCallContext, ToolExecutionResult
from app.agent.graph.runtime import GraphRuntimeContext

from ..state import ReplyState


def tool_executor_node(state: ReplyState, context: GraphRuntimeContext) -> ReplyState:
    # 只读取最后一条消息，因为工具调用只应该来自最近一次模型回复。
    last_message = state.messages[-1] if state.messages else None
    # 如果最后一条不是 AIMessage，说明当前没有可执行的工具调用，直接清空 latest_tool_results 返回。
    if not isinstance(last_message, AIMessage):
        return state.model_copy(update={"latest_tool_results": ()})

    # 复制当前消息序列，后续会把 ToolMessage 逐条追加进去。
    updated_messages = list(state.messages)
    # 收集当前这一轮刚执行出来的工具结果。
    latest_tool_results: list[ToolExecutionResult] = []
    # 组装工具执行上下文，供每个工具读取当前用户和会话信息。
    call_context = ToolCallContext(
        user_id=state.message.sender_id,
        im_type=state.message.im_type,
        chat_id=state.message.chat_id,
    )
    # 遍历最近一条 AIMessage 里的所有 tool_call。
    for tool_call in last_message.tool_calls:
        # 读取工具调用 ID。
        tool_call_id = tool_call.get("id")
        # 读取工具名称。
        tool_name = tool_call.get("name")
        # 读取工具参数。
        tool_args = tool_call.get("args")
        # 没有合法 tool_call_id 时跳过，避免后续 ToolMessage 无法关联。
        if not isinstance(tool_call_id, str) or not tool_call_id:
            continue
        # 没有合法工具名时也跳过。
        if not isinstance(tool_name, str) or not tool_name:
            continue
        # 调统一工具执行器真正执行业务工具。
        execution_result = context.tool_executor.execute(
            tool_name=tool_name,
            tool_args=tool_args,
            call_context=call_context,
            tool_call_id=tool_call_id,
        )
        # 没拿到执行结果就跳过当前调用。
        if execution_result is None:
            continue
        # 把这一条结果记入 latest_tool_results。
        latest_tool_results.append(execution_result)
        # 同时把工具文本结果封装成 ToolMessage 回写到消息序列中，供后续模型继续消费。
        updated_messages.append(
            ToolMessage(
                content=execution_result.text,
                tool_call_id=execution_result.tool_call_id,
            )
        )

    # 累计历史工具结果，方便全局观察整轮图里执行过什么工具。
    cumulative_tool_results = tuple([*state.tool_results, *latest_tool_results])
    # 返回更新后的消息序列、本轮工具结果和累计工具结果。
    return state.model_copy(
        update={
            "messages": tuple(updated_messages),
            "latest_tool_results": tuple(latest_tool_results),
            "tool_results": cumulative_tool_results,
        }
    )
