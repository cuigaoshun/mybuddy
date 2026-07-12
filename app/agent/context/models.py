from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.event.models import IncomingChatMessage
from app.memory.models import MemoryRecord, UserMemoryProfile


@dataclass(frozen=True, slots=True)
class ContextEvidenceBlock:
    """表示一条可供模型参考的历史证据片段。"""

    # 证据对应的原始消息 ID。
    message_id: str
    # 证据对应的消息类型，通常区分用户或助手。
    message_type: int
    # 证据对应消息发生的时间。
    message_time: datetime
    # 证据片段的纯文本内容。
    content_text: str


@dataclass(frozen=True, slots=True)
class ContextSessionSnapshot:
    """表示对模型有意义的轻量会话摘要。"""

    # 当前会话的 chat_id。
    chat_id: str
    # 当前会话类型，例如单聊或群聊。
    chat_type: str
    # 当前接入平台类型，例如飞书。
    im_type: str
    # 当前会话首次回复时间，用于帮助模型理解关系时长。
    first_reply_time: datetime | None
    # 当前会话最近一次回复时间，用于帮助模型理解最新互动时间。
    latest_reply_time: datetime | None


@dataclass(frozen=True, slots=True)
class ContextUserMemorySnapshot:
    """表示供模型消费的用户级长期记忆快照。"""

    long_term_memory_summary: str | None
    user_profile: UserMemoryProfile | None


@dataclass(frozen=True, slots=True)
class ContextBundle:
    """表示一次回复生成过程中完整的上下文输入包。"""

    # 系统提示词，用于稳定约束模型行为。
    system_prompt: str
    # 当前正在处理的用户消息。
    current_message: IncomingChatMessage
    # 会话的轻量快照信息。
    session_snapshot: ContextSessionSnapshot
    # 用户级长期记忆快照。
    user_memory_snapshot: ContextUserMemorySnapshot | None
    # 最近连续对话记录，按时间线供模型直接参考。
    recent_records: tuple[MemoryRecord, ...]
    # 预先召回出的历史证据块。
    evidence_blocks: tuple[ContextEvidenceBlock, ...]
