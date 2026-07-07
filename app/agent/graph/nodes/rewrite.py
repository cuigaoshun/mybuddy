from __future__ import annotations

from app.agent.graph.runtime import GraphRuntimeContext

from ..state import ReplyState


def rewrite_node(state: ReplyState, context: GraphRuntimeContext) -> ReplyState:
    # 当前 rewrite 节点还不依赖运行时上下文。
    del context
    # 第一阶段先做最轻量的查询规范化，只去掉两端空白。
    canonical_query = state.message.text.strip()
    # 预留 rewrite 说明列表，当前阶段还没有实际改写说明。
    rewrite_notes: tuple[str, ...] = ()
    # 如果 strip 之后为空，就回退到原始文本，避免把问题抹没。
    if canonical_query == "":
        canonical_query = state.message.text
    # 把规范化后的查询和 rewrite 说明写回状态。
    return state.model_copy(update={"canonical_query": canonical_query, "rewrite_notes": rewrite_notes})
