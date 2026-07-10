from __future__ import annotations

from app.event.models import IncomingChatMessage
from app.memory.models import ChatSessionInfo
from app.router.contracts import ChatAgent

from .state import ReplyState


class GraphChatAgent(ChatAgent):
    """基于 LangGraph 的聊天 Agent 封装。"""

    def __init__(
        self,
        compiled_graph,
    ) -> None:
        # 预编译后的状态图实例。
        self._compiled_graph = compiled_graph

    def generate_reply(self, message: IncomingChatMessage, session_info: ChatSessionInfo) -> str | None:
        """基于当前消息和会话信息生成回复文本。"""

        # 用当前消息和会话信息初始化 ReplyState，然后交给编译后的图执行。
        result = self._compiled_graph.invoke(
            ReplyState(
                message=message,
                session_info=session_info,
            )
        )
        # 最终只关心图状态里沉淀出来的 final_reply 字段。
        return result.get("final_reply")
