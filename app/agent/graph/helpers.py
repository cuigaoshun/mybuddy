from __future__ import annotations

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from app.agent.context.tools.models import ToolCategoryName

from .runtime import GraphRuntimeContext
from .state import ReplyState


def extract_selected_category(reply: AIMessage) -> ToolCategoryName | None:
    for tool_call in getattr(reply, "tool_calls", []) or []:
        if tool_call.get("name") != "select_tool_category":
            continue
        tool_args = tool_call.get("args")
        if not isinstance(tool_args, dict):
            continue
        category_name = tool_args.get("category_name")
        if category_name in {"history_tools", "memory_tools", "web_search_tools"}:
            return category_name
    return None


def has_non_selector_tool_call(reply: AIMessage) -> bool:
    for tool_call in getattr(reply, "tool_calls", []) or []:
        tool_name = tool_call.get("name")
        if isinstance(tool_name, str) and tool_name != "select_tool_category":
            return True
    return False


def invoke_model(model, messages: list[BaseMessage]) -> AIMessage:
    return model.invoke(messages)


def build_selector_messages(state: ReplyState, context: GraphRuntimeContext) -> list[BaseMessage]:
    base_messages = build_chat_messages(state=state, context=context)
    selector_instruction = SystemMessage(
        content="你可以直接调用核心工具；只有当需要非核心工具时，才调用 `select_tool_category` 先选择工具大类。若不需要工具，请直接自然回答，不要发起 tool call。"
    )
    return [selector_instruction, *base_messages]


def build_chat_messages(state: ReplyState, context: GraphRuntimeContext) -> list[BaseMessage]:
    if state.messages:
        return list(state.messages)
    if state.context_bundle is None:
        return [HumanMessage(content=state.message.text)]
    formatted_messages = list(context.context_formatter.format(state.context_bundle))
    trimmed_messages = context.context_budgeter.trim_messages(tuple(formatted_messages))
    return list(trimmed_messages)
