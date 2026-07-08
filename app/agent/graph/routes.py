from __future__ import annotations

from langchain_core.messages import AIMessage

from .constants import GraphNodes
from .state import ReplyState


def route_after_chat_model(state: ReplyState) -> GraphNodes:
    """根据 chat_model 的输出决定下一跳。"""

    # selector 刚完成时，优先立即回到 chat_model，让模型基于新开放工具继续下一轮。
    if state.selector_pending_chat_model:
        return GraphNodes.CHAT_MODEL
    # 取最后一条消息，判断主模型是否发起了 tool_call。
    last_message = state.messages[-1] if state.messages else None
    # 没有 tool_call 时说明本轮已经得到最终自然语言回复。
    if not isinstance(last_message, AIMessage) or not getattr(last_message, "tool_calls", None):
        return GraphNodes.END
    # 只要当前轮存在真实工具调用，就统一进入工具执行节点。
    return GraphNodes.EXECUTE_TOOLS
