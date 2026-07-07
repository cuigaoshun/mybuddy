from __future__ import annotations

from typing import Literal

from langchain_core.messages import AIMessage

from .state import ReplyState


def route_after_tool_selector(state: ReplyState) -> Literal["tool_expansion", "tool_executor", "end"]:
    # selector 已经直接产出最终回复时，当前图可以结束。
    if state.final_reply is not None:
        return "end"
    # selector 已经直接命中核心工具时，跳去执行工具。
    if state.selector_requires_tool_execution:
        return "tool_executor"
    # 其余情况说明只选中了工具大类，需要继续展开工具再调主模型。
    return "tool_expansion"


def route_after_chat_model(state: ReplyState) -> Literal["tool_executor", "end"]:
    # 取最后一条消息，判断主模型是否发起了工具调用。
    last_message = state.messages[-1] if state.messages else None
    # 只要最后一条是带 tool_calls 的 AIMessage，就进入工具执行。
    if isinstance(last_message, AIMessage) and getattr(last_message, "tool_calls", None):
        return "tool_executor"
    # 否则说明已经得到自然语言回复，直接结束。
    return "end"


def route_after_context_update(state: ReplyState) -> Literal["tool_selector", "end"]:
    # 超过最大工具轮次时，强制终止回路。
    if state.tool_round >= state.max_tool_rounds:
        return "end"
    # 否则带着更新后的上下文继续回到 selector 做下一轮决策。
    return "tool_selector"
