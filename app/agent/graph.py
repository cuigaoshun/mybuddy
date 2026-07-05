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
from app.agent.context.tools.models import ToolCallContext
from app.agent.util import extract_reply_text, messages_to_jsonable
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


def build_graph(chat_model: ChatModel, conversation_memory_service: ConversationMemoryService):
    # 在图外先准备好上下文构建、格式化和预算裁剪组件。
    context_builder = ConversationContextBuilder(conversation_memory_service)
    context_formatter = ConversationContextFormatter()
    context_budgeter = ContextMessageBudgeter(chat_model)
    tool_executor = ToolExecutor(context_builder.get_tool_registry())

    tool_enabled_chat_model = chat_model.bind_tools(context_builder.list_langchain_tools())

    def input_node(state: ReplyState) -> ReplyState:
        # 每轮进入模型前，都从最新的上下文包重新生成并裁剪 messages。
        messages = context_budgeter.trim_messages(context_formatter.format(state.context_bundle))
        return state.model_copy(update={"messages": messages})

    def reply_node(state: ReplyState) -> ReplyState:
        # 记录最终送模的 messages，方便后续排查上下文装配问题。
        messages = list(state.messages)
        logger.info("请求模型提示词:\n{}", json.dumps(messages_to_jsonable(messages), ensure_ascii=False, indent=2))
        reply = tool_enabled_chat_model.invoke(messages)
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

    def route(state: ReplyState) -> Literal["tool", "end"]:
        # 只有模型真的发起工具调用时，才进入工具节点继续补证据。
        if state.messages and isinstance(state.messages[-1], AIMessage) and getattr(state.messages[-1], "tool_calls", None):
            return "tool"
        return "end"

    graph = StateGraph(ReplyState)
    graph.add_node("input", input_node)
    graph.add_node("reply", reply_node)
    graph.add_node("tool", tool_node)
    graph.add_edge(START, "input")
    graph.add_edge("input", "reply")
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
            )
        )
        return result.get("reply_text")
