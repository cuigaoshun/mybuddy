from __future__ import annotations

from app.agent.graph.runtime import GraphRuntimeContext

from ..state import ReplyState


def load_memory_node(state: ReplyState, context: GraphRuntimeContext) -> ReplyState:
    """基于当前消息和会话信息构建初始上下文包。"""

    # 基于当前消息和会话信息构建初始上下文包。
    context_bundle = context.context_builder.build_initial_bundle(state.message, state.session_info)
    # 把初始上下文包写回图状态。
    return state.model_copy(update={"context_bundle": context_bundle})
