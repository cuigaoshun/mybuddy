from __future__ import annotations

from typing import Literal

from langchain_core.messages import BaseMessage
from pydantic import BaseModel, ConfigDict

from app.agent.context.models import ContextBundle
from app.agent.context.tools.models import ToolCategoryName, ToolExecutionResult, ToolSpec
from app.event.models import IncomingChatMessage
from app.memory.models import ChatSessionInfo


class ReplyState(BaseModel):
    """新回复图在图内流转的统一运行态。"""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    message: IncomingChatMessage
    session_info: ChatSessionInfo
    thread_id: str = ""
    context_bundle: ContextBundle | None = None
    messages: tuple[BaseMessage, ...] = ()
    canonical_query: str = ""
    rewrite_notes: tuple[str, ...] = ()
    selected_tool_categories: tuple[ToolCategoryName, ...] = ()
    selected_tool_names: tuple[str, ...] = ()
    selector_confidence: float | None = None
    selector_requires_tool_execution: bool = False
    active_tool_specs: tuple[ToolSpec, ...] = ()
    active_tool_names: tuple[str, ...] = ()
    latest_tool_results: tuple[ToolExecutionResult, ...] = ()
    tool_results: tuple[ToolExecutionResult, ...] = ()
    final_reply: str | None = None
    tool_round: int = 0
    max_tool_rounds: int = 3
