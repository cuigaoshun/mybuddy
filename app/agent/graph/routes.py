from __future__ import annotations

from typing import Literal

from langchain_core.messages import AIMessage

from .helpers import has_non_selector_tool_call
from .state import ReplyState


def route_after_tool_selector(state: ReplyState) -> Literal["core_tools", "chat_model", "end"]:
    """根据 selector 的输出决定下一跳。"""

    # selector 已经直接产出最终回复时，当前图可以结束。
    if state.final_reply is not None:
        return "end"
    # 取最后一条消息，判断 selector 是否已经直接发起了核心工具调用。
    last_message = state.messages[-1] if state.messages else None
    # 只要最后一条是带真实核心工具调用的 AIMessage，就先去执行核心工具。
    if isinstance(last_message, AIMessage) and has_non_selector_tool_call(last_message):
        return "core_tools"
    # 其余情况都先进入主模型，让主模型基于当前轮开放工具继续推理。
    return "chat_model"


def route_after_chat_model(state: ReplyState) -> Literal["core_tools", "dynamic_tools", "end"]:
    """根据 chat_model 的输出决定下一跳。"""

    # 取最后一条消息，判断主模型是否发起了 tool_call。
    last_message = state.messages[-1] if state.messages else None
    # 没有 tool_call 时说明本轮已经得到最终自然语言回复。
    if not isinstance(last_message, AIMessage) or not getattr(last_message, "tool_calls", None):
        return "end"
    # 没有选中非核心工具类别时，tool_call 只能由核心工具节点执行。
    if state.selected_tool_category is None:
        return "core_tools"
    # 已经选中非核心工具类别时，交给动态工具节点执行。
    return "dynamic_tools"
