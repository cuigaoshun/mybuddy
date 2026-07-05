from __future__ import annotations

from typing import Literal

from langchain_core.messages import AIMessage

from .state import ReplyState


def route_after_select_category(state: ReplyState) -> Literal["refresh_messages", "reply", "end"]:
    """selector 阶段后根据状态决定刷新消息、普通回复或直接结束。"""

    if state.reply_text is not None:
        return "end"
    if state.selected_tool_category is None:
        return "reply"
    return "refresh_messages"


def route_after_reply(state: ReplyState) -> Literal["tool", "end"]:
    """根据模型是否发起 tool call，决定继续工具回环还是直接结束。"""

    # 只有模型真的发起工具调用时，才进入工具节点继续补证据。
    if state.messages and isinstance(state.messages[-1], AIMessage) and getattr(state.messages[-1], "tool_calls", None):
        return "tool"
    return "end"
