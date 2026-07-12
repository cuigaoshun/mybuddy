from __future__ import annotations

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from app.agent.context.tools.selector import build_category_selector_tool
from app.agent.graph.constants import ToolPhase
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
    # 常规阶段把模型回复追加进消息历史。
    return _build_regular_reply_update(messages=messages, reply=reply)


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
    core_tools = context.tool_registry.list_core_tools()
    # 处于 selector 决策轮时，优先同时暴露 selector 工具和核心工具。
    if state.tool_phase == ToolPhase.AWAIT_SELECTOR:
        selector_tool = build_category_selector_tool(context.tool_registry.list_non_core_categories())
        return context.llm_provider.model().bind_tools([selector_tool, *core_tools])
    # selector 完成但未选中非核心工具时，只保留核心工具。
    if state.selected_tool_category is None:
        return context.llm_provider.model().bind_tools(core_tools)
    # selector 选中了非核心工具大类后，继续同时暴露核心工具与这些类别下的工具集合。
    return context.llm_provider.model().bind_tools(
        [*core_tools, *context.tool_registry.list_categories_tools(state.selected_tool_category)]
    )


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


def _build_regular_reply_update(
    messages: list[BaseMessage],
    reply: AIMessage,
) -> dict[str, object]:
    """构造常规聊天轮次的状态更新。"""

    updated_messages = tuple([*messages, reply])
    final_reply = None if getattr(reply, "tool_calls", None) else extract_reply_text(reply)
    return {
        "messages": updated_messages,
        "final_reply": final_reply,
        "tool_phase": ToolPhase.IDLE,
    }
