from __future__ import annotations

from typing import Literal

from langchain_core.messages import AIMessage

from .state import ReplyState


def route_after_tool_selector(state: ReplyState) -> Literal["tool_expansion", "tool_executor", "end"]:
    if state.final_reply is not None:
        return "end"
    if state.selector_requires_tool_execution:
        return "tool_executor"
    return "tool_expansion"


def route_after_chat_model(state: ReplyState) -> Literal["tool_executor", "end"]:
    last_message = state.messages[-1] if state.messages else None
    if isinstance(last_message, AIMessage) and getattr(last_message, "tool_calls", None):
        return "tool_executor"
    return "end"


def route_after_context_update(state: ReplyState) -> Literal["tool_selector", "end"]:
    if state.tool_round >= state.max_tool_rounds:
        return "end"
    return "tool_selector"
