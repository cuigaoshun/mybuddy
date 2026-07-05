from __future__ import annotations

from app.agent.context.budget import ContextMessageBudgeter
from app.agent.context.formatter import ConversationContextFormatter

from ...state import ReplyState


def input_node(
    state: ReplyState,
    context_formatter: ConversationContextFormatter,
    context_budgeter: ContextMessageBudgeter,
) -> ReplyState:
    """把上下文包格式化并裁剪成当前轮真正送模的 messages。"""

    # 每轮进入模型前，都从最新的上下文包重新生成并裁剪 messages。
    messages = context_budgeter.trim_messages(context_formatter.format(state.context_bundle))
    return state.model_copy(update={"messages": messages})
