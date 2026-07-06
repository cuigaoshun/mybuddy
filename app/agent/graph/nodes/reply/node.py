from __future__ import annotations

from loguru import logger

from app.agent.graph.runtime import GraphRuntimeContext
from app.agent.util import extract_reply_text

from ...helpers import invoke_model
from ...state import ReplyState


def reply_node(
    state: ReplyState,
    context: GraphRuntimeContext,
) -> ReplyState:
    """正式回复节点：普通直答或按已选大类动态绑定小工具后回复。"""

    # 第二阶段根据是否已选 category，决定是直接回答还是动态绑定该类小工具。
    messages = list(state.messages)
    logger.info(
        "reply阶段开始，selected_tool_category={}，bound_tool_count={}，message_count={}",
        state.selected_tool_category,
        len(state.context_bundle.enabled_tool_specs),
        len(messages),
    )
    if state.selected_tool_category is None:
        bound_tools_summary = "[]"
    else:
        bound_tools_summary = f"{state.selected_tool_category}: {[tool_spec.name for tool_spec in state.context_bundle.enabled_tool_specs]}"
    reply_model, resolved_bound_tools_summary = context.reply_model_resolver(state, context)
    reply = invoke_model(
        model=reply_model,
        messages=messages,
        bound_tools_summary=resolved_bound_tools_summary,
    )
    updated_messages = tuple([*messages, reply])
    if getattr(reply, "tool_calls", None):
        # 一旦模型发起工具调用，就把 AIMessage 保留给工具节点继续处理。
        return state.model_copy(update={"messages": updated_messages})
    # 否则说明本轮已经给出最终回复文本，可直接写回状态。
    return state.model_copy(update={"messages": updated_messages, "reply_text": extract_reply_text(reply)})
