from __future__ import annotations

from app.agent.context.builder import ConversationContextBuilder
from app.event.models import IncomingChatMessage
from app.memory.models import ChatSessionInfo

from .state import ReplyState


class GraphChatAgent:
    """基于 LangGraph 的聊天 Agent 封装。"""

    def __init__(
        self,
        compiled_graph,
        context_builder: ConversationContextBuilder,
    ) -> None:
        # 预编译后的状态图实例。
        self._compiled_graph = compiled_graph
        # 统一上下文构建器，负责在入图前准备 context bundle。
        self._context_builder = context_builder

    def generate_reply(self, message: IncomingChatMessage, session_info: ChatSessionInfo) -> str | None:
        """基于当前消息和会话信息生成回复文本。"""

        # 先构建统一上下文包，再交给图做回复与工具回环。
        context_bundle = self._context_builder.build_initial_bundle(message, session_info)
        # 用结构化状态启动整张图，让节点按既定流程推进。
        result = self._compiled_graph.invoke(
            ReplyState(
                message=message,
                session_info=session_info,
                context_bundle=context_bundle,
                selected_tool_category=None,
            )
        )
        # 图运行结束后，只取最终生成的回复文本返回给上层。
        return result.get("reply_text")
