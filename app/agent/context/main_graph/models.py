from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.event.models import IncomingChatMessage
from app.memory.models import MemoryRecord, UserMemoryProfile


@dataclass(frozen=True, slots=True)
class ContextEvidenceBlock:
    """表示一条可供模型参考的历史证据片段。"""

    message_id: str
    message_type: int
    message_time: datetime
    content_text: str


@dataclass(frozen=True, slots=True)
class ContextSessionSnapshot:
    """表示对模型有意义的轻量会话摘要。"""

    chat_id: str
    chat_type: str
    im_type: str
    first_reply_time: datetime | None
    latest_reply_time: datetime | None


@dataclass(frozen=True, slots=True)
class ContextUserMemorySnapshot:
    """表示供模型消费的用户级长期记忆快照。"""

    long_term_memory_summary: str | None
    user_profile: UserMemoryProfile | None


@dataclass(frozen=True, slots=True)
class ContextBundle:
    """表示一次回复生成过程中完整的上下文输入包。"""

    system_prompt: str
    current_message: IncomingChatMessage
    session_snapshot: ContextSessionSnapshot
    user_memory_snapshot: ContextUserMemorySnapshot | None
    recent_records: tuple[MemoryRecord, ...]
    evidence_blocks: tuple[ContextEvidenceBlock, ...]
