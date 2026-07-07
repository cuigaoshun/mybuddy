from __future__ import annotations

from app.agent.graph.runtime import GraphRuntimeContext

from ..state import ReplyState


def context_update_node(state: ReplyState, context: GraphRuntimeContext) -> ReplyState:
    # 先读取当前上下文包，后续会把工具结果继续补回去。
    context_bundle = state.context_bundle
    # 如果当前没有上下文包，就只能单纯推进工具轮次。
    if context_bundle is None:
        return state.model_copy(update={"tool_round": state.tool_round + 1})

    # 从当前上下文包开始逐条叠加本轮工具结果。
    next_bundle = context_bundle
    # latest_tool_results 只包含当前这一轮刚执行出来的工具结果。
    for execution_result in state.latest_tool_results:
        # 先把结构化历史结果补回上下文证据层。
        next_bundle = context.context_builder.append_tool_results(next_bundle, execution_result.structured_results)
        # 再把工具的文本摘要补回工具上下文层。
        next_bundle = context.context_builder.append_tool_context(
            next_bundle,
            tool_name=execution_result.tool_name,
            content_text=execution_result.text,
        )

    # 把更新后的上下文包写回状态，同时清空 latest_tool_results 并推进工具轮次。
    return state.model_copy(
        update={
            "context_bundle": next_bundle,
            "latest_tool_results": (),
            "tool_round": state.tool_round + 1,
        }
    )
