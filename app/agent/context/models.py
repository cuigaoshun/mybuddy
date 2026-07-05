from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from app.agent.context.tools.models import ToolCategory, ToolCategoryName, ToolSpec
from app.event.models import IncomingChatMessage
from app.memory.models import MemoryRecord

ContextEvidenceSource = Literal["similar_recall", "history_search"]


@dataclass(frozen=True, slots=True)
class ContextEvidenceBlock:
    message_id: str
    message_type: int
    message_time: datetime
    content_text: str
    source: ContextEvidenceSource
    matched_by_text: bool
    matched_by_vector: bool
    is_window_expanded: bool


@dataclass(frozen=True, slots=True)
class ContextSessionSnapshot:
    chat_id: str
    chat_type: str
    im_type: str
    first_reply_time: datetime | None
    latest_reply_time: datetime | None


@dataclass(frozen=True, slots=True)
class ContextBundle:
    system_prompt: str
    tool_selector_prompt: str | None
    tool_category_prompt: str | None
    current_message: IncomingChatMessage
    session_snapshot: ContextSessionSnapshot
    recent_records: tuple[MemoryRecord, ...]
    evidence_blocks: tuple[ContextEvidenceBlock, ...]
    enabled_tool_categories: tuple[ToolCategory, ...]
    enabled_tool_specs: tuple[ToolSpec, ...]
    selected_tool_category: ToolCategoryName | None = None
    tool_evidence_blocks: tuple[ContextEvidenceBlock, ...] = ()
