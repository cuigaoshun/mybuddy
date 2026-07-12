from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage, BaseMessage
from langgraph.types import Command

from app.agent.context.tools.selector import build_category_selector_tool
from app.agent.graph.constants import SELECT_TOOL_CATEGORY_TOOL_NAME, ToolPhase
from app.agent.graph.runtime import GraphRuntimeContext

from ..state import ReplyState


def apply_tool_selection_node(state: ReplyState, context: GraphRuntimeContext) -> dict[str, object]:
    """消费 selector 调用，并把真实工具调用继续留给后续执行节点。"""

    # selector 节点只关心当前最后一条 AI 回复，因为那是 chat_model 刚刚产出的本轮决策结果。
    last_reply = state.messages[-1] if state.messages else None
    # 如果最后一条消息根本不是 AIMessage，说明当前轮没有可消费的 selector 调用，
    # 这里按安全兜底处理成“未开放非核心工具，但仍完成了 selector 轮”。
    if not isinstance(last_reply, AIMessage):
        return _build_selector_only_update(state=state, selector_command=None)
    # 基于当前已注册的非核心工具大类，现场构造 selector 工具实例，保持与 chat_model 暴露给模型的定义一致。
    selector_tool = build_category_selector_tool(context.tool_registry.list_non_core_categories())
    # 先从模型这条回复里提取并真正执行 selector 调用，把“选择哪个大类”落成 Command(update=...)。
    selector_command = _extract_selector_command(selector_tool=selector_tool, reply=last_reply)
    # 再把同一条回复里的 selector tool_call 剥掉，只保留真实工具调用，避免 selector 泄漏到 execute_tools。
    real_tool_reply = _strip_selector_tool_calls(last_reply)
    # 如果同一条回复里既有 selector 又有真实工具，就走 mixed 路径：
    # 先应用 selector 结果，再把剥离后的真实工具调用继续留给 execute_tools 批量执行。
    if real_tool_reply is not None:
        return _build_selector_and_tool_reply_update(
            state=state,
            messages=state.messages[:-1],
            selector_command=selector_command,
            real_tool_reply=real_tool_reply,
        )
    # 否则说明当前轮只有 selector，没有真实工具调用；下一跳应回 chat_model 基于新工具集再生成一轮。
    return _build_selector_only_update(state=state, selector_command=selector_command)


def _extract_selector_command(selector_tool, reply: AIMessage) -> Command[Any] | None:
    # 遍历整条 AI 回复里的全部 tool_calls，只消费 selector 自己的调用，其余真实工具留给后续路径处理。
    for tool_call in getattr(reply, "tool_calls", []) or []:
        if tool_call.get("name") != SELECT_TOOL_CATEGORY_TOOL_NAME:
            continue
        # selector 参数理论上应该是 dict；如果模型给了别的结构，这里退化成空参调用，走工具自身兜底逻辑。
        tool_args = tool_call.get("args")
        result = selector_tool.invoke(tool_args if isinstance(tool_args, dict) else {})
        # 只接受 Command(update=...) 这种受控返回，避免把异常结构直接带入图状态。
        if isinstance(result, Command):
            return result
    return None


def _strip_selector_tool_calls(reply: AIMessage) -> AIMessage | None:
    # 把 selector 从当前回复中剥离后，只保留真实工具调用；这是防止 selector 落进 execute_tools 的关键一步。
    real_tool_calls = [
        tool_call
        for tool_call in getattr(reply, "tool_calls", []) or []
        if tool_call.get("name") != SELECT_TOOL_CATEGORY_TOOL_NAME
    ]
    # 如果剥离后一个真实工具都不剩，返回 None，表示这是 selector-only 路径。
    if not real_tool_calls:
        return None
    # 复制原始 AIMessage 并只替换 tool_calls，尽量保留原回复里的内容、ID 和其他元信息。
    return reply.model_copy(update={"tool_calls": real_tool_calls})


def _build_selector_only_update(
    state: ReplyState,
    selector_command: Command[Any] | None,
) -> dict[str, object]:
    # selector-only 路径下，不需要把任何 AIMessage 留给执行器，只要更新选择结果，
    # 并把工具阶段推进到“selector 已完成，等待再回 chat_model 一轮”。
    return {
        **_build_selector_selection_update(selector_command),
        **_build_tool_phase_update(state=state, tool_phase=ToolPhase.AWAIT_POST_SELECTOR_CHAT),
    }


def _build_selector_and_tool_reply_update(
    state: ReplyState,
    messages: tuple[BaseMessage, ...],
    selector_command: Command[Any] | None,
    real_tool_reply: AIMessage,
) -> dict[str, object]:
    # mixed 路径下，上一条原始 AIMessage 会被“剥离 selector 后的 AIMessage”替换，
    # 这样后续 routes / execute_tools 看到的就只剩真实工具调用，不会再误执行 selector。
    return {
        "messages": tuple([*messages, real_tool_reply]),
        **_build_selector_selection_update(selector_command),
        **_build_tool_phase_update(state=state, tool_phase=ToolPhase.IDLE),
    }


def _build_selector_selection_update(selector_command: Command[Any] | None) -> dict[str, object]:
    # 没拿到合法 Command 时，明确回退成“不开放非核心工具”的安全状态。
    if selector_command is None:
        return {"selected_tool_category": None}
    # selector 工具真正关心的只有 update 负载；其余 Command 字段当前图流程不消费。
    command_update = getattr(selector_command, "update", None)
    # update 结构不合法时同样按安全状态处理，避免 selector 输出污染图状态。
    if not isinstance(command_update, dict):
        return {"selected_tool_category": None}
    # 复制一份 dict 返回，避免把底层对象引用直接暴露给后续状态更新逻辑。
    return dict(command_update)


def _build_tool_phase_update(
    state: ReplyState,
    tool_phase: ToolPhase,
) -> dict[str, ToolPhase | int]:
    # selector 节点每完成一次消费，都推进一次 tool_round，
    # 这样 selector-only 和 mixed 路径都能统一计入工具回路预算。
    return {
        "tool_phase": tool_phase,
        "tool_round": state.tool_round + 1,
    }
