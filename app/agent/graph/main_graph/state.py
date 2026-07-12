from __future__ import annotations

from langchain_core.messages import BaseMessage
from pydantic import BaseModel, ConfigDict

from app.agent.context.main_graph.models import ContextBundle
from app.agent.context.tools.models import ToolCategorySelection
from app.agent.graph.main_graph.constants import ToolPhase
from app.event.models import IncomingChatMessage
from app.memory.models import ChatSessionInfo, MemoryRecord, RetrievedMemoryHit, UserMemory


class ReplyState(BaseModel):
    """新回复图在图内流转的统一运行态。"""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    message: IncomingChatMessage
    session_info: ChatSessionInfo
    recent_records: tuple[MemoryRecord, ...] = ()
    user_memory: UserMemory | None = None
    retrieved_memory_hits: tuple[RetrievedMemoryHit, ...] = ()
    reranked_memory_hits: tuple[RetrievedMemoryHit, ...] = ()
    context_bundle: ContextBundle | None = None
    messages: tuple[BaseMessage, ...] = ()
    selected_tool_category: ToolCategorySelection | None = None
    tool_phase: ToolPhase = ToolPhase.AWAIT_SELECTOR
    final_reply: str | None = None
    tool_round: int = 0
    max_tool_rounds: int = 10
