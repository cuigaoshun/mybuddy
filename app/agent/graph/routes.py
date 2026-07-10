from __future__ import annotations

from langchain_core.messages import AIMessage

from .constants import GraphNodes
from .state import ReplyState


def route_after_chat_model(state: ReplyState) -> GraphNodes:
    """根据 chat_model 的输出决定下一跳。"""

    # selector 刚完成时，优先立即回到 chat_model，让模型基于新开放工具继续下一轮。
    if state.selector_pending_chat_model:
        return GraphNodes.CHAT_MODEL
    # 倒序找到最近一条 AIMessage，避免末尾恰好不是 AIMessage 时误判路由。
    last_ai_message = next(
        (
            message
            for message in reversed(state.messages)
            if isinstance(message, AIMessage)
        ),
        None,
    )
    # 没有任何 AI 回复时，说明当前轮无法继续走工具分支，直接结束。
    if last_ai_message is None:
        return GraphNodes.END
    # 最近一条 AI 回复没有 tool_call 时，说明本轮已经得到最终自然语言回复。
    if not last_ai_message.tool_calls:
        return GraphNodes.END
    # 只要当前轮存在真实工具调用，就统一进入工具执行节点。
    return GraphNodes.EXECUTE_TOOLS
