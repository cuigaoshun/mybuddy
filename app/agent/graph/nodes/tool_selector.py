from __future__ import annotations

from loguru import logger
from app.agent.context.tools.selector import build_category_selector_tool
from langchain_core.messages import AIMessage
from app.agent.util import extract_reply_text

from app.agent.graph.runtime import GraphRuntimeContext

from .. import helpers
from ..state import ReplyState


def tool_selector_node(state: ReplyState, context: GraphRuntimeContext) -> ReplyState:
    core_tool_specs = context.tool_registry.list_core_tool_specs()
    core_tools = [tool_spec.tool for tool_spec in core_tool_specs]
    core_tool_names = tuple(tool_spec.name for tool_spec in core_tool_specs)
    selector_tool = build_category_selector_tool(context.tool_registry.list_non_core_categories())
    selector_model = context.llm_provider.model().bind_tools([selector_tool, *core_tools])
    messages = helpers.build_selector_messages(state, context)
    reply = helpers.invoke_model(model=selector_model, messages=messages, bound_tool_names=("select_tool_category", *core_tool_names))
    selected_category = helpers.extract_selected_category(reply)
    updated_messages = tuple([*messages, reply])
    if _has_non_selector_tool_call(reply):
        logger.info("tool_selector 直接命中核心工具调用")
        return state.model_copy(
            update={
                "messages": updated_messages,
                "selected_tool_categories": (),
                "selected_tool_names": (),
                "selector_confidence": 0.9,
                "selector_requires_tool_execution": True,
            }
        )
    direct_reply_text = _extract_direct_reply_text(reply)
    if direct_reply_text is not None:
        logger.info("tool_selector 已直接产出最终回复，结束当前轮")
        return state.model_copy(
            update={
                "messages": updated_messages,
                "final_reply": direct_reply_text,
                "selected_tool_categories": (),
                "selected_tool_names": (),
                "selector_confidence": 1.0,
                "selector_requires_tool_execution": False,
            }
        )
    if selected_category is None:
        logger.info("tool_selector 未选择工具大类，当前轮按直答继续")
        return state.model_copy(
            update={
                "messages": updated_messages,
                "selected_tool_categories": (),
                "selected_tool_names": (),
                "selector_confidence": 0.4,
                "selector_requires_tool_execution": False,
            }
        )
    tool_specs = context.tool_registry.list_tool_specs_by_category(selected_category)
    selected_tool_names = tuple(tool_spec.name for tool_spec in tool_specs)
    logger.info("tool_selector 选中工具大类={} tools={}", selected_category, selected_tool_names)
    return state.model_copy(
        update={
            "selected_tool_categories": (selected_category,),
            "selected_tool_names": selected_tool_names,
            "selector_confidence": 0.9,
            "selector_requires_tool_execution": False,
        }
    )


def _has_non_selector_tool_call(reply: AIMessage) -> bool:
    for tool_call in getattr(reply, "tool_calls", []) or []:
        tool_name = tool_call.get("name")
        if isinstance(tool_name, str) and tool_name != "select_tool_category":
            return True
    return False


def _extract_direct_reply_text(reply: AIMessage) -> str | None:
    if getattr(reply, "tool_calls", None):
        return None
    reply_text = extract_reply_text(reply).strip()
    if reply_text == "":
        return None
    return reply_text
