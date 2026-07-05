from __future__ import annotations

from loguru import logger

from app.agent.context.builder import ConversationContextBuilder
from app.agent.util import extract_reply_text

from ...helpers import invoke_model
from ...state import ReplyState


def reply_node(
    state: ReplyState,
    chat_model,
    context_builder: ConversationContextBuilder,
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
    if state.selected_tool_category is None:
        # 没有选中任何工具大类时，走普通聊天模型直答。
        reply = invoke_model(
            model=chat_model,
            messages=messages,
            bound_tools_summary=bound_tools_summary,
        )
    else:
        # 只按选中的大类动态绑定对应小工具，减少无关 schema 进入上下文。
        category_tool_model = chat_model.bind_tools(
            context_builder.list_langchain_tools_by_category(state.selected_tool_category)
        )
        reply = invoke_model(
            model=category_tool_model,
            messages=messages,
            bound_tools_summary=bound_tools_summary,
        )
    updated_messages = tuple([*messages, reply])
    if getattr(reply, "tool_calls", None):
        # 一旦模型发起工具调用，就把 AIMessage 保留给工具节点继续处理。
        return state.model_copy(update={"messages": updated_messages})
    # 否则说明本轮已经给出最终回复文本，可直接写回状态。
    return state.model_copy(update={"messages": updated_messages, "reply_text": extract_reply_text(reply)})
