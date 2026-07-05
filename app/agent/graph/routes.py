from __future__ import annotations

from typing import Literal

from langchain_core.messages import AIMessage

from .state import ReplyState


def route_after_select_category(state: ReplyState) -> Literal["reply"]:
    """大类选择阶段结束后，固定进入正式回复阶段。"""

    return "reply"


def route_after_reply(state: ReplyState) -> Literal["tool", "end"]:
    """根据模型是否发起 tool call，决定继续工具回环还是直接结束。"""

    # 只有模型真的发起工具调用时，才进入工具节点继续补证据。
    if state.messages and isinstance(state.messages[-1], AIMessage) and getattr(state.messages[-1], "tool_calls", None):
        return "tool"
    return "end"
