from __future__ import annotations

from typing import Literal

from .state import ReplyState


def route_after_tool_selector(state: ReplyState) -> Literal["tool_expansion", "tool_executor"]:
    if state.selector_requires_tool_execution:
        return "tool_executor"
    return "tool_expansion"


def route_after_decision(state: ReplyState) -> Literal["tool_selector", "tool_executor", "end"]:
    return state.next_step or "end"
