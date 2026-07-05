from __future__ import annotations

from typing import Literal

from langchain_core.messages import AIMessage

from .state import ReplyState


def route_after_select_tool(state: ReplyState) -> Literal["refresh_messages", "reply", "tool", "end"]:
    """首阶段选工具后，根据状态决定走分类分支、直接回复、首阶段工具执行或结束。"""

    if state.reply_text is not None:
        return "end"
    if state.selected_tool_category is None:
        if state.messages and isinstance(state.messages[-1], AIMessage) and getattr(state.messages[-1], "tool_calls", None):
            return "tool"
        return "reply"
    return "refresh_messages"


def route_after_refresh_messages(state: ReplyState) -> Literal["reply", "select_tool"]:
    if state.selected_tool_category is None and not state.tool_selection_completed:
        return "select_tool"
    return "reply"


def route_after_tool(state: ReplyState) -> Literal["refresh_messages", "reply"]:
    if state.refresh_after_tool:
        return "refresh_messages"
    return "reply"


def route_after_reply(state: ReplyState) -> Literal["tool", "end"]:
    """根据模型是否发起 tool call，决定继续工具回环还是直接结束。"""

    # 只有模型真的发起工具调用时，才进入工具节点继续补证据。
    if state.messages and isinstance(state.messages[-1], AIMessage) and getattr(state.messages[-1], "tool_calls", None):
        return "tool"
    return "end"
