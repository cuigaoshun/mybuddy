from __future__ import annotations

from loguru import logger

from app.agent.graph.runtime import GraphRuntimeContext

from ...helpers import extract_selected_category, extract_selector_reply_text, has_non_category_tool_call, invoke_model
from ...state import ReplyState


def select_tool_node(
    state: ReplyState,
    context: GraphRuntimeContext,
) -> ReplyState:
    """第一阶段节点：先统一决定是否直接调工具，或先选择工具大类。"""

    messages = list(state.messages)
    entry_tool_specs = state.context_bundle.enabled_tool_specs
    bound_tool_names = ["select_tool_category", *[tool_spec.name for tool_spec in entry_tool_specs]]
    logger.info(
        "select_tool阶段开始，category_count={}，tool_count={}，message_count={}，selected_tool_category={}",
        len(state.context_bundle.enabled_tool_categories),
        len(entry_tool_specs),
        len(messages),
        state.selected_tool_category,
    )
    tool_selector_model = context.selector_model_resolver(state, context)
    reply = invoke_model(
        model=tool_selector_model,
        messages=messages,
        bound_tools_summary=str(bound_tool_names),
    )
    updated_messages = tuple([*messages, reply])
    selected_category = extract_selected_category(reply)
    if has_non_category_tool_call(reply):
        logger.info("select_tool阶段直接选中了具体工具，进入工具执行")
        return state.model_copy(
            update={
                "messages": updated_messages,
                "tool_selection_completed": True,
                "refresh_after_tool": True,
            }
        )
    if selected_category is None:
        selector_reply_text = extract_selector_reply_text(reply)
        if selector_reply_text is not None:
            logger.info("select_tool阶段直接给出最终回复，结束图流程")
            return state.model_copy(
                update={
                    "messages": updated_messages,
                    "reply_text": selector_reply_text,
                    "tool_selection_completed": True,
                    "refresh_after_tool": False,
                }
            )
        logger.info("select_tool阶段未选工具，转入普通回复")
        return state.model_copy(
            update={
                "messages": updated_messages,
                "tool_selection_completed": True,
                "refresh_after_tool": False,
            }
    )
    logger.info("select_tool阶段选中工具大类：{}", selected_category)
    next_bundle = context.context_builder.select_tool_category(state.context_bundle, selected_category)
    return state.model_copy(
        update={
            "messages": updated_messages,
            "context_bundle": next_bundle,
            "selected_tool_category": selected_category,
            "tool_selection_completed": True,
            "refresh_after_tool": False,
        }
    )


def select_category_node(
    state: ReplyState,
    context: GraphRuntimeContext,
) -> ReplyState:
    return select_tool_node(
        state=state,
        context=context,
    )
