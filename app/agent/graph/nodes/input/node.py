from __future__ import annotations

from app.agent.graph.runtime import GraphRuntimeContext

from ...state import ReplyState


def input_node(
    state: ReplyState,
    context: GraphRuntimeContext,
) -> ReplyState:
    """把上下文包格式化并裁剪成当前轮真正送模的 messages。"""

    # 每轮进入模型前，都从最新的上下文包重新生成并裁剪 messages。
    messages = context.context_budgeter.trim_messages(context.context_formatter.format(state.context_bundle))
    return state.model_copy(update={"messages": messages})


def refresh_messages_node(
    state: ReplyState,
    context: GraphRuntimeContext,
) -> ReplyState:
    """选定工具大类后，基于新上下文包重新生成第二阶段送模消息。"""

    # 这里只刷新消息，不再重新进入 selector 阶段，避免工具大类被重复选择。
    messages = context.context_budgeter.trim_messages(context.context_formatter.format(state.context_bundle))
    return state.model_copy(update={"messages": messages, "refresh_after_tool": False})
