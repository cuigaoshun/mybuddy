from __future__ import annotations

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from app.agent.context.tools.selector import build_category_selector_tool
from app.agent.graph.main_graph.constants import ToolPhase
from app.agent.graph.main_graph.runtime import GraphRuntimeContext
from app.agent.util import extract_reply_text

from ..state import ReplyState


def chat_model_node(state: ReplyState, context: GraphRuntimeContext) -> dict[str, object]:
    messages = _build_chat_messages(state, context)
    model = _build_chat_model(state=state, context=context)
    reply = _invoke_model(model=model, messages=messages)
    return _build_regular_reply_update(messages=messages, reply=reply)


def _invoke_model(model, messages: list[BaseMessage]) -> AIMessage:
    return model.invoke(messages)


def _build_chat_messages(state: ReplyState, context: GraphRuntimeContext) -> list[BaseMessage]:
    if state.messages:
        return list(state.messages)
    if state.context_bundle is None:
        return [HumanMessage(content=state.message.text)]
    formatted_messages = list(context.context_tool.formatter.format(state.context_bundle))
    return list(formatted_messages)


def _build_chat_model(state: ReplyState, context: GraphRuntimeContext):
    if state.tool_round >= state.max_tool_rounds:
        return context.llm_provider.model()
    core_tools = context.tool_registry.list_core_tools()
    if state.tool_phase == ToolPhase.AWAIT_SELECTOR:
        selector_tool = build_category_selector_tool(context.tool_registry.list_non_core_categories())
        return context.llm_provider.model().bind_tools([selector_tool, *core_tools])
    if state.selected_tool_category is None:
        return context.llm_provider.model().bind_tools(core_tools)
    return context.llm_provider.model().bind_tools(
        [*core_tools, *context.tool_registry.list_categories_tools(state.selected_tool_category)]
    )


def _build_regular_reply_update(messages: list[BaseMessage], reply: AIMessage) -> dict[str, object]:
    updated_messages = tuple([*messages, reply])
    final_reply = None if reply.tool_calls else extract_reply_text(reply)
    return {
        "messages": updated_messages,
        "final_reply": final_reply,
        "tool_phase": ToolPhase.IDLE,
    }
