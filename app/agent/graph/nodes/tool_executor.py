from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.tools import BaseTool
from langgraph.prebuilt import ToolNode
from langgraph.runtime import Runtime

from app.agent.context.tools.selector import build_category_selector_tool
from app.agent.graph.constants import SELECT_TOOL_CATEGORY_TOOL_NAME, ToolPhase
from app.agent.graph.runtime import GraphRuntimeContext
from langgraph.types import Command

from ..state import ReplyState


@dataclass(frozen=True, slots=True)
class SelectorResolution:
    """表示当前最后一条 AIMessage 中 selector 调用的解析结果。"""

    # 当前这条 AIMessage 是否真的包含了 selector 调用。
    found: bool
    # 若包含 selector，则这里记录它最终开放的非核心工具类别；
    # 为 None 时表示“调用了 selector，但结果是不开放任何非核心工具”。
    selected_tool_category: Any


def execute_tools_node(
    state: ReplyState,
    context: GraphRuntimeContext,
    runtime: Runtime,
) -> dict[str, object]:
    # 只在最后一条消息确实是 AI tool_call 回复时才继续执行工具。
    last_message = state.messages[-1] if state.messages else None
    # 如果最后一条消息不是模型发起的 tool_calls，说明当前轮没有任何真实工具需要执行，直接空返回。
    if not isinstance(last_message, AIMessage):
        return {}
    # 先在执行层统一消费 selector：更新 selected_tool_category，并把 selector tool_call 从消息中剥离。
    selector_tool = build_category_selector_tool(context.tool_registry.list_non_core_categories())
    selector_resolution = _resolve_selector_selection(selector_tool=selector_tool, reply=last_message)
    # 当前轮允许执行的工具集合 = 核心工具 + 当前已开放的动态工具集合。
    effective_category = _resolve_effective_selected_category(state=state, selector_resolution=selector_resolution)
    allowed_tool_names = _build_allowed_tool_names(state=state, context=context, selected_tool_category=effective_category)
    # 基于当前允许执行的工具集合构造 ToolNode，让 ToolRuntime 自动注入当前图状态。
    tool_node = ToolNode(_build_allowed_tools(context=context, allowed_tool_names=allowed_tool_names))
    # 把 selector 从当前最后一条 AIMessage 中剥离，只让执行器看到真实工具调用。
    sanitized_state = _strip_selector_tool_calls_from_state(state)
    # 如果剥离后已经没有任何真实工具调用，就不需要再执行 ToolNode，
    # 当前轮只需带着新的 selected_tool_category 回到 chat_model 即可。
    sanitized_last_message = sanitized_state.messages[-1] if sanitized_state.messages else None
    if not isinstance(sanitized_last_message, AIMessage) or not sanitized_last_message.tool_calls:
        return {
            "messages": sanitized_state.messages,
            "selected_tool_category": effective_category,
            "tool_phase": _build_post_selector_phase(selector_resolution),
            "tool_round": state.tool_round + 1,
        }
    # 用过滤后的状态真正执行工具，让 ToolNode 只看到当前最后一条 AIMessage 里的真实工具调用。
    result = tool_node.invoke(sanitized_state, runtime=runtime)
    # 从 ToolNode 的返回结构里只提取 ToolMessage，避免把其他中间字段误写回图状态。
    outputs = _extract_tool_messages(result)
    # 本轮没有任何工具真正执行时，直接保持原状态返回。
    if not outputs:
        return {
            "messages": sanitized_state.messages,
            "selected_tool_category": effective_category,
            "tool_phase": ToolPhase.IDLE,
            "tool_round": state.tool_round + 1,
        }
    # 工具真正执行成功后，把产出的 ToolMessage 追加回消息历史，并推进一次工具轮次计数。
    return {
        "messages": tuple([*sanitized_state.messages, *outputs]),
        "selected_tool_category": effective_category,
        "tool_phase": ToolPhase.IDLE,
        "tool_round": state.tool_round + 1,
    }


def _build_allowed_tool_names(
    state: ReplyState,
    context: GraphRuntimeContext,
    selected_tool_category,
) -> set[str]:
    # 核心工具始终可用，它们不依赖 selector 开放。
    allowed_tool_names = set(context.tool_registry.list_core_tool_names())
    # 若当前没有开放任何非核心类别，就直接返回核心工具集合。
    if selected_tool_category is None:
        return allowed_tool_names
    # 否则把 selector 已开放的那些类别下的真实工具名合并进来，供本轮执行使用。
    allowed_tool_names.update(context.tool_registry.list_categories_tool_names(selected_tool_category))
    return allowed_tool_names


def _build_allowed_tools(
    context: GraphRuntimeContext,
    allowed_tool_names: set[str],
) -> list[BaseTool]:
    # 这里按工具名回查 registry，确保 execute_tools 真正拿到的都是已注册、可执行的真实工具对象。
    return [context.tool_registry.get(tool_name) for tool_name in allowed_tool_names]


def _extract_tool_messages(result) -> tuple[ToolMessage, ...]:
    # LangGraph ToolNode 返回的是一个 dict，其中 messages 里可能混有不同消息类型；
    # 这里我们只保留真正代表工具执行结果的 ToolMessage。
    if isinstance(result, dict):
        tool_messages = result.get("messages", [])
        if isinstance(tool_messages, list):
            return tuple(message for message in tool_messages if isinstance(message, ToolMessage))
    return ()


def _resolve_selector_selection(selector_tool, reply: AIMessage) -> SelectorResolution:
    # 返回一个显式对象，而不是靠哨兵值区分：
    # found=False 表示这一轮没有 selector 调用；
    # found=True 且 selected_tool_category=None 表示调用了 selector，但结果是“不开放非核心工具”；
    # found=True 且 selected_tool_category=tuple[...] 表示开放了对应类别。
    for tool_call in reply.tool_calls or []:
        if tool_call.get("name") != SELECT_TOOL_CATEGORY_TOOL_NAME:
            continue
        tool_args = tool_call.get("args")
        result = selector_tool.invoke(tool_args if isinstance(tool_args, dict) else {})
        if isinstance(result, Command):
            command_update = getattr(result, "update", None)
            if isinstance(command_update, dict):
                return SelectorResolution(
                    found=True,
                    selected_tool_category=command_update.get("selected_tool_category"),
                )
            return SelectorResolution(found=True, selected_tool_category=None)
    return SelectorResolution(found=False, selected_tool_category=None)


def _resolve_effective_selected_category(state: ReplyState, selector_resolution: SelectorResolution):
    if not selector_resolution.found:
        return state.selected_tool_category
    return selector_resolution.selected_tool_category


def _build_post_selector_phase(selector_resolution: SelectorResolution) -> ToolPhase:
    # 只有当这一轮确实出现过 selector 调用，且剥离后没有任何真实工具可执行时，
    # 才需要回 chat_model 基于新的 selected_tool_category 再生成一轮。
    if not selector_resolution.found:
        return ToolPhase.IDLE
    return ToolPhase.AWAIT_POST_SELECTOR_CHAT


def _strip_selector_tool_calls_from_state(state: ReplyState) -> ReplyState:
    # execute_tools 只应该消费最后一条 AIMessage，因为当前图的真实工具执行语义就是“执行本轮最新工具调用”。
    last_message = state.messages[-1] if state.messages else None
    # 没有最后一条 AIMessage 时无需过滤，原状态直接返回。
    if not isinstance(last_message, AIMessage):
        return state
    # 把 selector 工具调用剥掉，只保留真正应该交给 ToolNode 的真实工具调用。
    sanitized_tool_calls = [
        tool_call
        for tool_call in last_message.tool_calls
        if tool_call.get("name") != SELECT_TOOL_CATEGORY_TOOL_NAME
    ]
    # 如果过滤前后数量一致，说明根本没有 selector 泄漏，直接复用原状态即可。
    if len(sanitized_tool_calls) == len(last_message.tool_calls):
        return state
    # 否则复制最后一条 AIMessage 并替换 tool_calls，保持其它元信息不变。
    sanitized_last_message = last_message.model_copy(update={"tool_calls": sanitized_tool_calls})
    # 最后只替换消息序列的最后一条，让执行器看到的状态与上游图状态保持最小差异。
    return state.model_copy(update={"messages": (*state.messages[:-1], sanitized_last_message)})
