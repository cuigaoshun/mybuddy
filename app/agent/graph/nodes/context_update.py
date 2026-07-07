from __future__ import annotations

from app.agent.graph.runtime import GraphRuntimeContext

from ..state import ReplyState


def context_update_node(state: ReplyState, context: GraphRuntimeContext) -> ReplyState:
    context_bundle = state.context_bundle
    if context_bundle is None:
        return state.model_copy(update={"tool_round": state.tool_round + 1})

    next_bundle = context_bundle
    for execution_result in state.latest_tool_results:
        next_bundle = context.context_builder.append_tool_results(next_bundle, execution_result.structured_results)
        next_bundle = context.context_builder.append_tool_context(
            next_bundle,
            tool_name=execution_result.tool_name,
            content_text=execution_result.text,
        )

    return state.model_copy(
        update={
            "context_bundle": next_bundle,
            "latest_tool_results": (),
            "tool_round": state.tool_round + 1,
        }
    )
