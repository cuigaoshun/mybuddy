from __future__ import annotations

from langchain_core.messages import AIMessage

from app.agent.graph.main_graph.constants import GraphNodes
from app.agent.graph.main_graph.state import ReplyState


def route_after_chat_model(state: ReplyState) -> GraphNodes:
    """根据 chat_model 的输出决定下一跳。"""

    last_ai_message = next((message for message in reversed(state.messages) if isinstance(message, AIMessage)), None)
    if last_ai_message is None:
        return GraphNodes.END
    if not last_ai_message.tool_calls:
        return GraphNodes.END
    return GraphNodes.EXECUTE_TOOLS
