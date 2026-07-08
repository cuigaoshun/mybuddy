from __future__ import annotations

from langchain_core.messages import AIMessage, ToolMessage
from langgraph.prebuilt import ToolNode

from app.agent.context.tools.history_tools.search_history import bind_history_tool_state, reset_history_tool_state
from app.agent.graph.runtime import GraphRuntimeContext

from ..state import ReplyState


def core_tools_node(state: ReplyState, context: GraphRuntimeContext) -> ReplyState:
    # 基于当前注册的核心工具构造一个 LangGraph 原生 ToolNode。
    tool_node = ToolNode(context.tool_registry.list_core_tools())
    # 把当前累计消息传给 ToolNode，让它执行最后一条 AIMessage 里的核心工具调用。
    result = tool_node.invoke({"messages": list(state.messages)})
    # 从 ToolNode 返回结果里取出本轮新增的 ToolMessage 列表。
    tool_messages = tuple(result.get("messages", []))
    # 把工具执行结果继续追加回图状态，并累计工具轮次计数。
    return state.model_copy(
        update={
            "messages": tuple([*state.messages, *tool_messages]),
            "tool_round": state.tool_round + 1,
        }
    )


def dynamic_tool_node(state: ReplyState, context: GraphRuntimeContext) -> ReplyState:
    # 只在最后一条消息确实是 AI tool_call 回复时才继续执行动态工具。
    last_message = state.messages[-1] if state.messages else None
    if not isinstance(last_message, AIMessage):
        return state
    # 把当前已选中的多个工具大类合并成这一轮允许执行的动态工具白名单。
    allowed_tool_names = set(context.tool_registry.list_categories_tool_names(state.selected_tool_category)) if state.selected_tool_category else set()
    # 收集本轮实际执行后产出的 ToolMessage，稍后统一回写到消息历史。
    outputs: list[ToolMessage] = []
    # 先把当前图状态绑定给动态工具，供历史工具等按当前会话上下文执行。
    state_token = bind_history_tool_state(state)
    try:
        # 逐个执行模型这轮发起的 tool_call。
        for call in last_message.tool_calls:
            tool_name = call.get("name")
            tool_call_id = call.get("id")
            tool_args = call.get("args")
            # 不在当前多类白名单里的工具调用直接跳过。
            if not isinstance(tool_name, str) or tool_name not in allowed_tool_names:
                continue
            # 缺少合法 tool_call_id 时，无法构造可追踪的 ToolMessage，也直接跳过。
            if not isinstance(tool_call_id, str) or tool_call_id == "":
                continue
            # 真正调用工具并把结果包装成 ToolMessage，供下一轮模型继续消费。
            result = context.tool_registry.get(tool_name).invoke(tool_args if isinstance(tool_args, dict) else {})
            outputs.append(ToolMessage(content=str(result), tool_call_id=tool_call_id))
    finally:
        # 无论执行成功与否，都要恢复动态工具上下文绑定。
        reset_history_tool_state(state_token)
    # 本轮没有任何动态工具真正执行时，直接保持原状态返回。
    if not outputs:
        return state
    return state.model_copy(
        update={
            "messages": tuple([*state.messages, *outputs]),
            "tool_round": state.tool_round + 1,
        }
    )
