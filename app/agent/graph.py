from __future__ import annotations

import json
from typing import Literal

from langchain_core.messages import AIMessage, BaseMessage, ToolMessage
from langgraph.graph import END, START, StateGraph
from loguru import logger
from pydantic import BaseModel, ConfigDict

from app.agent.context.builder import ConversationContextBuilder
from app.agent.context.budget import ContextMessageBudgeter
from app.agent.context.formatter import ConversationContextFormatter
from app.agent.context.models import ContextBundle
from app.agent.context.tools import ToolExecutor
from app.agent.context.tools.models import ToolCallContext, ToolCategoryName
from app.agent.util import extract_reply_text, messages_to_jsonable, tool_specs_to_jsonable
from app.event.models import IncomingChatMessage
from app.memory.models import ChatSessionInfo
from app.memory.service import ConversationMemoryService
from app.services.llm import ChatModel


class ReplyState(BaseModel):
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    message: IncomingChatMessage
    session_info: ChatSessionInfo
    context_bundle: ContextBundle
    reply_text: str | None = None
    messages: tuple[BaseMessage, ...] = ()
    selected_tool_category: ToolCategoryName | None = None


def build_graph(chat_model: ChatModel, conversation_memory_service: ConversationMemoryService):
    # 在图外先准备好上下文构建、格式化和预算裁剪组件。
    context_builder = ConversationContextBuilder(conversation_memory_service)
    context_formatter = ConversationContextFormatter()
    context_budgeter = ContextMessageBudgeter(chat_model)
    tool_executor = ToolExecutor(context_builder.get_tool_registry())
    category_selector_tool = context_builder.build_category_selector_tool()
    category_selector_model = chat_model.bind_tools([category_selector_tool])

    def input_node(state: ReplyState) -> ReplyState:
        # 每轮进入模型前，都从最新的上下文包重新生成并裁剪 messages。
        messages = context_budgeter.trim_messages(context_formatter.format(state.context_bundle))
        return state.model_copy(update={"messages": messages})

    def select_category_node(state: ReplyState) -> ReplyState:
        # 第一阶段只绑定 selector tool，让模型先决定是否需要工具和选哪个大类。
        messages = list(state.messages)
        logger.info(
            "当前绑定工具 schema:\n{}",
            json.dumps(tool_specs_to_jsonable(state.context_bundle.enabled_tool_specs), ensure_ascii=False, indent=2),
        )
        logger.info("请求模型提示词:\n{}", json.dumps(messages_to_jsonable(messages), ensure_ascii=False, indent=2))
        reply = category_selector_model.invoke(messages)
        updated_messages = tuple([*messages, reply])
        selected_category = _extract_selected_category(reply)
        if selected_category is None:
            return state.model_copy(update={"messages": updated_messages})
        next_bundle = context_builder.select_tool_category(state.context_bundle, selected_category)
        return state.model_copy(
            update={
                "messages": updated_messages,
                "context_bundle": next_bundle,
                "selected_tool_category": selected_category,
            }
        )

    def reply_node(state: ReplyState) -> ReplyState:
        # 第二阶段根据是否已选 category，决定是直接回答还是动态绑定该类小工具。
        messages = list(state.messages)
        logger.info(
            "当前绑定工具 schema:\n{}",
            json.dumps(tool_specs_to_jsonable(state.context_bundle.enabled_tool_specs), ensure_ascii=False, indent=2),
        )
        logger.info("请求模型提示词:\n{}", json.dumps(messages_to_jsonable(messages), ensure_ascii=False, indent=2))
        if state.selected_tool_category is None:
            reply = chat_model.invoke(messages)
        else:
            category_tool_model = chat_model.bind_tools(
                context_builder.list_langchain_tools_by_category(state.selected_tool_category)
            )
            reply = category_tool_model.invoke(messages)
        updated_messages = tuple([*messages, reply])
        if getattr(reply, "tool_calls", None):
            return state.model_copy(update={"messages": updated_messages})
        return state.model_copy(update={"messages": updated_messages, "reply_text": extract_reply_text(reply)})

    def tool_node(state: ReplyState) -> ReplyState:
        last_message = state.messages[-1]
        if not isinstance(last_message, AIMessage):
            return state

        # 工具查询只负责补充上下文证据，不直接重写主时间线消息。
        updated_messages = list(state.messages)
        next_bundle = state.context_bundle
        call_context = ToolCallContext(
            user_id=state.message.sender_id,
            im_type=state.message.im_type,
            chat_id=state.message.chat_id,
        )
        for tool_call in last_message.tool_calls:
            tool_call_id = tool_call.get("id")
            if not isinstance(tool_call_id, str) or not tool_call_id:
                continue
            tool_name = tool_call.get("name")
            if not isinstance(tool_name, str) or not tool_name:
                continue
            tool_args = tool_call.get("args")
            # 先由模型决定小工具，再由执行器路由到对应实现。
            execution_result = tool_executor.execute(
                tool_name=tool_name,
                tool_args=tool_args,
                call_context=call_context,
                tool_call_id=tool_call_id,
            )
            if execution_result is None:
                continue
            next_bundle = context_builder.append_tool_results(next_bundle, execution_result.structured_results)
            updated_messages.append(
                ToolMessage(
                    content=execution_result.text,
                    tool_call_id=execution_result.tool_call_id,
                )
            )

        return state.model_copy(
            update={
                "messages": tuple(updated_messages),
                "context_bundle": next_bundle,
            }
        )

    def route_after_select_category(state: ReplyState) -> Literal["reply"]:
        return "reply"

    def route(state: ReplyState) -> Literal["tool", "end"]:
        # 只有模型真的发起工具调用时，才进入工具节点继续补证据。
        if state.messages and isinstance(state.messages[-1], AIMessage) and getattr(state.messages[-1], "tool_calls", None):
            return "tool"
        return "end"

    graph = StateGraph(ReplyState)
    graph.add_node("input", input_node)
    graph.add_node("select_category", select_category_node)
    graph.add_node("reply", reply_node)
    graph.add_node("tool", tool_node)
    graph.add_edge(START, "input")
    graph.add_edge("input", "select_category")
    graph.add_conditional_edges("select_category", route_after_select_category, {"reply": "reply"})
    graph.add_conditional_edges("reply", route, {"tool": "tool", "end": END})
    graph.add_edge("tool", "reply")
    return graph.compile()


class GraphChatAgent:
    def __init__(
        self,
        compiled_graph,
        context_builder: ConversationContextBuilder,
    ) -> None:
        self._compiled_graph = compiled_graph
        self._context_builder = context_builder

    def generate_reply(self, message: IncomingChatMessage, session_info: ChatSessionInfo) -> str | None:
        # 先构建统一上下文包，再交给图做回复与工具回环。
        context_bundle = self._context_builder.build_initial_bundle(message, session_info)
        result = self._compiled_graph.invoke(
            ReplyState(
                message=message,
                session_info=session_info,
                context_bundle=context_bundle,
                selected_tool_category=None,
            )
        )
        return result.get("reply_text")


def _extract_selected_category(reply: AIMessage) -> ToolCategoryName | None:
    # 第一阶段只关心 selector tool 是否返回了合法的大类选择。
    for tool_call in getattr(reply, "tool_calls", []) or []:
        if tool_call.get("name") != "select_tool_category":
            continue
        tool_args = tool_call.get("args")
        if not isinstance(tool_args, dict):
            continue
        category_name = tool_args.get("category_name")
        if category_name in {"history_tools", "memory_tools"}:
            return category_name
    return None
