from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.tools import BaseTool
from langgraph.prebuilt import ToolNode
from langgraph.runtime import Runtime
from langgraph.types import Command

from app.agent.context.tools.selector import build_category_selector_tool
from app.agent.graph.main_graph.constants import SELECT_TOOL_CATEGORY_TOOL_NAME, ToolPhase
from app.agent.graph.main_graph.runtime import GraphRuntimeContext

from ..state import ReplyState


@dataclass(frozen=True, slots=True)
class SelectorResolution:
    found: bool
    selected_tool_category: Any


def execute_tools_node(state: ReplyState, context: GraphRuntimeContext, runtime: Runtime) -> dict[str, object]:
    last_message = state.messages[-1] if state.messages else None
    if not isinstance(last_message, AIMessage):
        return {}
    selector_tool = build_category_selector_tool(context.tool_registry.list_non_core_categories())
    selector_resolution = _resolve_selector_selection(selector_tool=selector_tool, reply=last_message)
    effective_category = _resolve_effective_selected_category(state=state, selector_resolution=selector_resolution)
    allowed_tool_names = _build_allowed_tool_names(state=state, context=context, selected_tool_category=effective_category)
    tool_node = ToolNode(_build_allowed_tools(context=context, allowed_tool_names=allowed_tool_names))
    sanitized_state = _strip_selector_tool_calls_from_state(state)
    sanitized_last_message = sanitized_state.messages[-1] if sanitized_state.messages else None
    if not isinstance(sanitized_last_message, AIMessage) or not sanitized_last_message.tool_calls:
        return {
            "messages": sanitized_state.messages,
            "selected_tool_category": effective_category,
            "tool_phase": _build_post_selector_phase(selector_resolution),
            "tool_round": state.tool_round + 1,
        }
    result = tool_node.invoke(sanitized_state, runtime=runtime)
    outputs = _extract_tool_messages(result)
    if not outputs:
        return {
            "messages": sanitized_state.messages,
            "selected_tool_category": effective_category,
            "tool_phase": ToolPhase.IDLE,
            "tool_round": state.tool_round + 1,
        }
    return {
        "messages": tuple([*sanitized_state.messages, *outputs]),
        "selected_tool_category": effective_category,
        "tool_phase": ToolPhase.IDLE,
        "tool_round": state.tool_round + 1,
    }


def _build_allowed_tool_names(state: ReplyState, context: GraphRuntimeContext, selected_tool_category) -> set[str]:
    allowed_tool_names = set(context.tool_registry.list_core_tool_names())
    if selected_tool_category is None:
        return allowed_tool_names
    allowed_tool_names.update(context.tool_registry.list_categories_tool_names(selected_tool_category))
    return allowed_tool_names


def _build_allowed_tools(context: GraphRuntimeContext, allowed_tool_names: set[str]) -> list[BaseTool]:
    return [context.tool_registry.get(tool_name) for tool_name in allowed_tool_names]


def _extract_tool_messages(result) -> tuple[ToolMessage, ...]:
    if isinstance(result, dict):
        tool_messages = result.get("messages", [])
        if isinstance(tool_messages, list):
            return tuple(message for message in tool_messages if isinstance(message, ToolMessage))
    return ()


def _resolve_selector_selection(selector_tool, reply: AIMessage) -> SelectorResolution:
    for tool_call in reply.tool_calls or []:
        if tool_call.get("name") != SELECT_TOOL_CATEGORY_TOOL_NAME:
            continue
        tool_args = tool_call.get("args")
        result = selector_tool.invoke(tool_args if isinstance(tool_args, dict) else {})
        if isinstance(result, Command):
            command_update = getattr(result, "update", None)
            if isinstance(command_update, dict):
                return SelectorResolution(found=True, selected_tool_category=command_update.get("selected_tool_category"))
            return SelectorResolution(found=True, selected_tool_category=None)
    return SelectorResolution(found=False, selected_tool_category=None)


def _resolve_effective_selected_category(state: ReplyState, selector_resolution: SelectorResolution):
    if not selector_resolution.found:
        return state.selected_tool_category
    return selector_resolution.selected_tool_category


def _build_post_selector_phase(selector_resolution: SelectorResolution) -> ToolPhase:
    if not selector_resolution.found:
        return ToolPhase.IDLE
    return ToolPhase.AWAIT_POST_SELECTOR_CHAT


def _strip_selector_tool_calls_from_state(state: ReplyState) -> ReplyState:
    last_message = state.messages[-1] if state.messages else None
    if not isinstance(last_message, AIMessage):
        return state
    sanitized_tool_calls = [tool_call for tool_call in last_message.tool_calls if tool_call.get("name") != SELECT_TOOL_CATEGORY_TOOL_NAME]
    if len(sanitized_tool_calls) == len(last_message.tool_calls):
        return state
    sanitized_last_message = last_message.model_copy(update={"tool_calls": sanitized_tool_calls})
    return state.model_copy(update={"messages": (*state.messages[:-1], sanitized_last_message)})
