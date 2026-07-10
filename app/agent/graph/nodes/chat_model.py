from __future__ import annotations

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langgraph.types import Command

from app.agent.context.tools.selector import build_category_selector_tool
from app.agent.graph.runtime import GraphRuntimeContext
from app.agent.util import extract_reply_text

from ..state import ReplyState


def chat_model_node(state: ReplyState, context: GraphRuntimeContext) -> dict[str, object]:
    # 先构建当前轮真正送给模型的消息序列。
    messages = _build_chat_messages(state, context)
    # 再根据当前状态决定本轮要绑定哪些工具。
    model = _build_chat_model(state=state, context=context)
    # 调模型拿到本轮回复。
    reply = _invoke_model(model=model, messages=messages)
    # 只要当前轮仍处于 selector 阶段，或再次调用了 selector 工具，就统一走 selector 分支处理。
    if _should_handle_selector_reply(state=state, reply=reply):
        return _handle_selector_reply(state=state, context=context, messages=messages, reply=reply)
    # 常规阶段把模型回复追加进消息历史。
    updated_messages = tuple([*messages, reply])
    # 只有没有 tool_call 时，当前轮才算拿到最终自然语言回复。
    final_reply = None if getattr(reply, "tool_calls", None) else extract_reply_text(reply)
    return {
        "messages": updated_messages,
        "final_reply": final_reply,
        # 常规回复轮次不需要再强制 router 回到 chat_model。
        "selector_pending_chat_model": False,
    }


def _has_non_selector_tool_call(reply: AIMessage) -> bool:
    """判断当前回复里是否存在非 selector 的真实工具调用。"""

    # 遍历模型返回的全部工具调用。
    for tool_call in getattr(reply, "tool_calls", []) or []:
        # 读取当前工具名称。
        tool_name = tool_call.get("name")
        # 只要存在非 selector 的工具调用，就说明模型要直接执行真实工具。
        if isinstance(tool_name, str) and tool_name != "select_tool_category":
            return True
    # 否则说明当前轮没有真实工具调用。
    return False


def _invoke_model(model, messages: list[BaseMessage]) -> AIMessage:
    """用当前消息序列直接调用模型。"""

    return model.invoke(messages)


def _build_chat_messages(state: ReplyState, context: GraphRuntimeContext) -> list[BaseMessage]:
    """构建当前轮真正送给模型的消息序列。"""

    # 如果图状态里已经有累计消息，优先直接复用，避免重复格式化。
    if state.messages:
        return list(state.messages)
    # 如果当前轮还没构建上下文包，就退化成只发送用户原始消息。
    if state.context_bundle is None:
        return [HumanMessage(content=state.message.text)]
    # 先把结构化上下文格式化成完整消息序列。
    formatted_messages = list(context.context_tool.formatter.format(state.context_bundle))
    # 这里先直接返回格式化结果，后续如果恢复预算裁剪可在这里插入。
    return list(formatted_messages)


def _build_chat_model(state: ReplyState, context: GraphRuntimeContext):
    """根据当前状态决定本轮模型需要暴露哪些工具。"""

    # 超过最大工具轮次后，直接退回纯聊天模型，避免无限循环。
    if state.tool_round >= state.max_tool_rounds:
        return context.llm_provider.model()
    # 所有工具轮次都继续暴露 selector 工具，允许模型在后续轮次重新选择或扩展工具大类。
    selector_tool = build_category_selector_tool(context.tool_registry.list_non_core_categories())
    core_tools = context.tool_registry.list_core_tools()
    # selector 阶段优先同时暴露 selector 工具和核心工具。
    if not state.selector_resolved:
        return context.llm_provider.model().bind_tools([selector_tool, *core_tools])
    # selector 完成但未选中非核心工具时，只保留核心工具。
    if state.selected_tool_category is None:
        return context.llm_provider.model().bind_tools([selector_tool, *core_tools])
    # selector 选中了非核心工具大类后，继续同时暴露核心工具与这些类别下的工具集合。
    return context.llm_provider.model().bind_tools(
        [selector_tool, *core_tools, *context.tool_registry.list_categories_tools(state.selected_tool_category)]
    )


def _handle_selector_reply(
    state: ReplyState,
    context: GraphRuntimeContext,
    messages,
    reply,
) -> dict[str, object]:
    """处理 selector 阶段的模型回复，并把状态推进到下一步。"""

    # 基于当前非核心工具类别构造 selector 工具实例。
    selector_tool = build_category_selector_tool(context.tool_registry.list_non_core_categories())
    # 如果模型显式调用了 selector，就真正执行它并读取返回的 Command。
    selector_command = _invoke_selector_tool(selector_tool=selector_tool, reply=reply)
    if selector_command is not None:
        return _apply_selector_command(state=state, selector_command=selector_command)
    # 如果 selector 阶段已经直接命中核心工具，就按核心工具分支继续走。
    if _has_non_selector_tool_call(reply):
        return {
            "messages": tuple([*messages, reply]),
            "selected_tool_category": None,
            **_build_selector_status_update(state=state, should_reenter_chat_model=False),
        }
    # 没有 tool_call 时，说明 selector 阶段可以直接给用户自然语言回复。
    direct_reply_text = _extract_direct_reply_text(reply)
    if direct_reply_text is not None:
        return {
            "final_reply": direct_reply_text,
            **_build_selector_status_update(state=state, should_reenter_chat_model=False),
        }
    # 其余情况说明当前轮没有工具也没有直接回复，按安全兜底结束 selector 阶段。
    return _apply_selector_command(state=state, selector_command=None)


def _extract_direct_reply_text(reply) -> str | None:
    """提取 selector 阶段直接给用户的自然语言回复文本。"""

    # 只要还有 tool_call，就说明当前回复不能视为直接自然语言结果。
    if getattr(reply, "tool_calls", None):
        return None
    # 统一抽取文本并裁掉前后空白。
    reply_text = extract_reply_text(reply).strip()
    # 空文本按无效结果处理。
    if reply_text == "":
        return None
    return reply_text


def _has_selector_tool_call(reply) -> bool:
    """判断模型回复里是否显式调用了 selector 工具。"""

    # 遍历全部工具调用，只要命中 selector 名称就返回 True。
    for tool_call in getattr(reply, "tool_calls", []) or []:
        if tool_call.get("name") == "select_tool_category":
            return True
    return False


def _should_handle_selector_reply(state: ReplyState, reply) -> bool:
    """判断当前回复是否仍应走 selector 阶段处理分支。"""

    # 只要 selector 还没结束，或者当前轮再次调用了 selector，都继续走 selector 逻辑。
    return (not state.selector_resolved) or _has_selector_tool_call(reply)


def _invoke_selector_tool(selector_tool, reply) -> Command | None:
    """从模型回复里提取 selector 调用并真正执行该工具。"""

    # 从模型返回的 tool_calls 里找到 selector 调用并真正执行它。
    for tool_call in getattr(reply, "tool_calls", []) or []:
        if tool_call.get("name") != "select_tool_category":
            continue
        tool_args = tool_call.get("args")
        result = selector_tool.invoke(tool_args if isinstance(tool_args, dict) else {})
        # 只接受 selector 工具返回的 Command 更新结果。
        if isinstance(result, Command):
            return result
    return None


def _apply_selector_command(state: ReplyState, selector_command: Command | None) -> dict[str, object]:
    """把 selector 工具返回的 Command 合并回图状态。"""

    # 没拿到合法 Command 时，回退成“selector 已完成，但未开放非核心工具”的状态。
    if selector_command is None:
        return {
            "selected_tool_category": None,
            **_build_selector_status_update(state=state, should_reenter_chat_model=True),
        }
    # 读取 selector 工具给出的状态更新内容。
    command_update = getattr(selector_command, "update", None)
    # update 结构不合法时，也退回到只开放核心工具的安全状态。
    if not isinstance(command_update, dict):
        return {
            "selected_tool_category": None,
            **_build_selector_status_update(state=state, should_reenter_chat_model=True),
        }
    # 正常情况下合并 selector 的选择结果，并通知 router 立即回到 chat_model。
    updated_state = {
        **command_update,
        **_build_selector_status_update(state=state, should_reenter_chat_model=True),
    }
    return updated_state


def _build_selector_status_update(
    state: ReplyState,
    should_reenter_chat_model: bool,
) -> dict[str, bool | int]:
    """构造 selector 阶段通用的状态更新片段。"""

    # selector 一旦跑过就标记为已解决，并同步推进工具轮次计数。
    return {
        "selector_resolved": True,
        "selector_pending_chat_model": should_reenter_chat_model,
        "tool_round": state.tool_round + 1,
    }
