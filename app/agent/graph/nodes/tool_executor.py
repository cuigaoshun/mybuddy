from __future__ import annotations

from langchain_core.messages import AIMessage, ToolMessage

from app.agent.context.tools.history_tools.search_history import bind_history_tool_state, reset_history_tool_state
from app.agent.graph.runtime import GraphRuntimeContext

from ..state import ReplyState


def execute_tools_node(state: ReplyState, context: GraphRuntimeContext) -> ReplyState:
    # 只在最后一条消息确实是 AI tool_call 回复时才继续执行工具。
    last_message = state.messages[-1] if state.messages else None
    if not isinstance(last_message, AIMessage):
        return state
    # 当前轮允许执行的工具集合 = 核心工具 + 当前已开放的动态工具集合。
    allowed_tool_names = _build_allowed_tool_names(state=state, context=context)
    # 收集本轮实际执行后产出的 ToolMessage，稍后统一回写到消息历史。
    outputs: list[ToolMessage] = []
    # 先把当前图状态绑定给工具执行上下文，供历史工具等按当前会话上下文执行。
    state_token = bind_history_tool_state(state)
    try:
        # 逐个执行模型这轮发起的 tool_call。
        outputs.extend(_execute_tool_calls(last_message=last_message, context=context, allowed_tool_names=allowed_tool_names))
    finally:
        # 无论执行成功与否，都要恢复工具上下文绑定。
        reset_history_tool_state(state_token)
    # 本轮没有任何工具真正执行时，直接保持原状态返回。
    if not outputs:
        return state
    return state.model_copy(
        update={
            "messages": tuple([*state.messages, *outputs]),
            "tool_round": state.tool_round + 1,
        }
    )


def _build_allowed_tool_names(state: ReplyState, context: GraphRuntimeContext) -> set[str]:
    allowed_tool_names = set(context.tool_registry.list_core_tool_names())
    if state.selected_tool_category is None:
        return allowed_tool_names
    allowed_tool_names.update(context.tool_registry.list_categories_tool_names(state.selected_tool_category))
    return allowed_tool_names


def _execute_tool_calls(
    last_message: AIMessage,
    context: GraphRuntimeContext,
    allowed_tool_names: set[str],
) -> list[ToolMessage]:
    outputs: list[ToolMessage] = []
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
    return outputs
