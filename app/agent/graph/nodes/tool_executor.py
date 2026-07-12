from __future__ import annotations

from langchain_core.messages import AIMessage, ToolMessage
from langgraph.prebuilt import ToolNode
from langgraph.runtime import Runtime

from app.agent.graph.runtime import GraphRuntimeContext

from ..state import ReplyState


def execute_tools_node(
    state: ReplyState,
    context: GraphRuntimeContext,
    runtime: Runtime,
) -> dict[str, object]:
    # 只在最后一条消息确实是 AI tool_call 回复时才继续执行工具。
    last_message = state.messages[-1] if state.messages else None
    if not isinstance(last_message, AIMessage):
        return {}
    # 当前轮允许执行的工具集合 = 核心工具 + 当前已开放的动态工具集合。
    allowed_tool_names = _build_allowed_tool_names(state=state, context=context)
    # 基于当前允许执行的工具集合构造 ToolNode，让 ToolRuntime 自动注入当前图状态。
    tool_node = ToolNode(_build_allowed_tools(context=context, allowed_tool_names=allowed_tool_names))
    result = tool_node.invoke(state, runtime=runtime)
    outputs = _extract_tool_messages(result)
    # 本轮没有任何工具真正执行时，直接保持原状态返回。
    if not outputs:
        return {}
    return {
        "messages": tuple([*state.messages, *outputs]),
        "tool_round": state.tool_round + 1,
    }


def _build_allowed_tool_names(state: ReplyState, context: GraphRuntimeContext) -> set[str]:
    allowed_tool_names = set(context.tool_registry.list_core_tool_names())
    if state.selected_tool_category is None:
        return allowed_tool_names
    allowed_tool_names.update(context.tool_registry.list_categories_tool_names(state.selected_tool_category))
    return allowed_tool_names


def _build_allowed_tools(
    context: GraphRuntimeContext,
    allowed_tool_names: set[str],
) -> list:
    return [context.tool_registry.get(tool_name) for tool_name in allowed_tool_names]


def _extract_tool_messages(result) -> tuple[ToolMessage, ...]:
    if isinstance(result, dict):
        tool_messages = result.get("messages", [])
        if isinstance(tool_messages, list):
            return tuple(message for message in tool_messages if isinstance(message, ToolMessage))
    return ()
