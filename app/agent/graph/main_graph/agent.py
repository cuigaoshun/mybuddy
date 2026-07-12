from __future__ import annotations

from app.event.models import IncomingChatMessage
from app.memory.models import ChatSessionInfo
from app.router.contracts import ChatAgent

from .state import ReplyState


class GraphChatAgent(ChatAgent):
    """基于 LangGraph 的聊天 Agent 封装。"""

    def __init__(self, compiled_graph) -> None:
        self._compiled_graph = compiled_graph

    def generate_reply(self, message: IncomingChatMessage, session_info: ChatSessionInfo) -> str | None:
        result = self._compiled_graph.invoke(ReplyState(message=message, session_info=session_info))
        return result.get("final_reply")
