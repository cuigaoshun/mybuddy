from __future__ import annotations

from loguru import logger
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from app.agent.context.tools.models import ToolCategoryName
from app.agent.util import format_messages_for_log

from .runtime import GraphRuntimeContext
from .state import ReplyState


def extract_selected_category(reply: AIMessage) -> ToolCategoryName | None:
    """从 selector tool 的 tool_calls 里提取被选中的工具大类。"""

    # 第一阶段只关心 selector tool 是否返回了合法的大类选择。
    for tool_call in getattr(reply, "tool_calls", []) or []:
        # 只解析大类选择工具，忽略其他 tool call。
        if tool_call.get("name") != "select_tool_category":
            continue
        tool_args = tool_call.get("args")
        # 参数结构不对时直接跳过，避免污染后续状态。
        if not isinstance(tool_args, dict):
            continue
        category_name = tool_args.get("category_name")
        # 目前仅接受仓库里声明过的合法工具大类。
        if category_name in {"history_tools", "memory_tools", "web_search_tools"}:
            return category_name
    return None


def has_non_selector_tool_call(reply: AIMessage) -> bool:
    for tool_call in getattr(reply, "tool_calls", []) or []:
        tool_name = tool_call.get("name")
        if isinstance(tool_name, str) and tool_name != "select_tool_category":
            return True
    return False


def invoke_model(model, messages: list[BaseMessage], bound_tool_names: tuple[str, ...] = ()) -> AIMessage:
    """统一封装模型调用并记录日志。"""

    logger.info("当前 bind_tools: {}", list(bound_tool_names))
    logger.info("请求模型提示词:\n{}", format_messages_for_log(messages))
    reply = model.invoke(messages)
    logger.info(
        "模型回复: text={} tool_calls={}",
        getattr(reply, "content", ""),
        getattr(reply, "tool_calls", []),
    )
    return reply


def build_selector_messages(state: ReplyState, context: GraphRuntimeContext) -> list[BaseMessage]:
    base_messages = _format_state_messages(state=state, context=context)
    selector_instruction = SystemMessage(
        content="你可以直接调用核心工具；只有当需要非核心工具时，才调用 `select_tool_category` 先选择工具大类。若不需要工具，请直接自然回答，不要发起 tool call。"
    )
    return [selector_instruction, *base_messages]


def build_chat_messages(state: ReplyState, context: GraphRuntimeContext) -> list[BaseMessage]:
    return _format_state_messages(state=state, context=context)


def _format_state_messages(
    state: ReplyState,
    context: GraphRuntimeContext,
) -> list[BaseMessage]:
    if state.context_bundle is None:
        return [HumanMessage(content=state.canonical_query or state.message.text)]

    formatted_messages = list(context.context_formatter.format(state.context_bundle))
    if formatted_messages and isinstance(formatted_messages[-1], HumanMessage):
        final_question = state.canonical_query or state.message.text
        formatted_messages[-1] = HumanMessage(content=final_question)
    if state.rewrite_notes:
        rewrite_note_message = SystemMessage(content="Rewrite 说明：\n- " + "\n- ".join(state.rewrite_notes))
        insert_index = 1 if formatted_messages and isinstance(formatted_messages[0], SystemMessage) else 0
        formatted_messages.insert(insert_index, rewrite_note_message)
    trimmed_messages = context.context_budgeter.trim_messages(tuple(formatted_messages))
    return list(trimmed_messages)
