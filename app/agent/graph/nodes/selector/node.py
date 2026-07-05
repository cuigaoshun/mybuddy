from __future__ import annotations

from loguru import logger

from app.agent.context.builder import ConversationContextBuilder

from ...helpers import extract_selected_category, extract_selector_reply_text, invoke_model
from ...state import ReplyState


def select_category_node(
    state: ReplyState,
    category_selector_model,
    context_builder: ConversationContextBuilder,
) -> ReplyState:
    """第一阶段节点：先判断要不要工具，并选出工具大类。"""

    # 第一阶段只绑定 selector tool，让模型先决定是否需要工具和选哪个大类。
    messages = list(state.messages)
    logger.info(
        "selector阶段开始，category_count={}，message_count={}，selected_tool_category={}",
        len(state.context_bundle.enabled_tool_categories),
        len(messages),
        state.selected_tool_category,
    )
    # 这一轮调用只允许模型产出 category 选择，不暴露业务小工具 schema。
    reply = invoke_model(
        model=category_selector_model,
        messages=messages,
        bound_tools_summary="[select_tool_category]",
    )
    updated_messages = tuple([*messages, reply])
    selected_category = extract_selected_category(reply)
    if selected_category is None:
        selector_reply_text = extract_selector_reply_text(reply)
        if selector_reply_text is not None:
            logger.info("selector阶段直接给出最终回复，结束图流程")
            return state.model_copy(update={"messages": updated_messages, "reply_text": selector_reply_text})
        # 如果模型没有选工具大类，后续就按普通回复路径继续。
        logger.info("selector阶段未选择工具大类，转入普通回复")
        return state.model_copy(update={"messages": updated_messages})
    # 一旦选中大类，就把上下文包收窄到该大类的小工具集合。
    logger.info("selector阶段选中工具大类：{}", selected_category)
    next_bundle = context_builder.select_tool_category(state.context_bundle, selected_category)
    return state.model_copy(
        update={
            "messages": updated_messages,
            "context_bundle": next_bundle,
            "selected_tool_category": selected_category,
        }
    )
