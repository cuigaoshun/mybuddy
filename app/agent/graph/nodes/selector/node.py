from __future__ import annotations

import json

from loguru import logger

from app.agent.context.builder import ConversationContextBuilder
from app.agent.util import messages_to_jsonable, tool_specs_to_jsonable

from ...helpers import extract_selected_category
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
        "当前绑定工具 schema:\n{}",
        json.dumps(tool_specs_to_jsonable(state.context_bundle.enabled_tool_specs), ensure_ascii=False, indent=2),
    )
    logger.info("请求模型提示词:\n{}", json.dumps(messages_to_jsonable(messages), ensure_ascii=False, indent=2))
    # 这一轮调用只允许模型产出 category 选择，不暴露业务小工具 schema。
    reply = category_selector_model.invoke(messages)
    updated_messages = tuple([*messages, reply])
    selected_category = extract_selected_category(reply)
    if selected_category is None:
        # 如果模型没有选工具大类，后续就按普通回复路径继续。
        return state.model_copy(update={"messages": updated_messages})
    # 一旦选中大类，就把上下文包收窄到该大类的小工具集合。
    next_bundle = context_builder.select_tool_category(state.context_bundle, selected_category)
    return state.model_copy(
        update={
            "messages": updated_messages,
            "context_bundle": next_bundle,
            "selected_tool_category": selected_category,
        }
    )
