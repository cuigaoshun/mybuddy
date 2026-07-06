from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from app.event.models import IncomingChatMessage
from app.memory.models import MemoryRecord

ContextEvidenceSource = Literal["similar_recall", "history_search"]


@dataclass(frozen=True, slots=True)
class ToolContextBlock:
    tool_name: str
    content_text: str


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
    current_message: IncomingChatMessage
    session_snapshot: ContextSessionSnapshot
    recent_records: tuple[MemoryRecord, ...]
    evidence_blocks: tuple[ContextEvidenceBlock, ...]
    tool_evidence_blocks: tuple[ContextEvidenceBlock, ...] = ()
    tool_context_blocks: tuple[ToolContextBlock, ...] = ()
