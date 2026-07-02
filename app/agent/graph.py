from __future__ import annotations

from typing import Literal

from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, ConfigDict

from typing import Final

from app.event.models import IncomingChatMessage

GREETING_TEXT: Final[str] = "你好"


class ReplyState(BaseModel):
    model_config = ConfigDict(frozen=True)

    message: IncomingChatMessage
    reply_text: str | None = None


def input_node(state: ReplyState) -> ReplyState:
    return state


def reply_node(state: ReplyState) -> ReplyState:
    return state.model_copy(update={"reply_text": state.message.text + "吗？"})


def route(_: ReplyState) -> Literal["reply"]:
    return "reply"


def build_graph():
    graph = StateGraph(ReplyState)
    graph.add_node("input", input_node)
    graph.add_node("reply", reply_node)
    graph.add_edge(START, "input")
    graph.add_conditional_edges("input", route)
    graph.add_edge("reply", END)
    return graph.compile()


GRAPH = build_graph()


def build_reply(message: IncomingChatMessage) -> str | None:
    """Return a reply for the supported hello demo."""
    result = GRAPH.invoke(ReplyState(message=message))
    return result.get("reply_text")
