from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app.storage.models import MemoryRecord


class ReminderScheduleStatus(StrEnum):
    """提醒规则状态。"""

    ACTIVE = "active"
    PAUSED = "paused"
    CANCELLED = "cancelled"


class ReminderJobStatus(StrEnum):
    """提醒执行任务状态。"""

    PENDING = "pending"
    RUNNING = "running"
    SENT = "sent"
    RETRYABLE_FAILED = "retryable_failed"
    BLOCKED_USER_ROUTE = "blocked_user_route"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class ReminderSchedule:
    """提醒规则定义。"""

    id: int | None
    user_id: str
    im_type: str
    chat_id: str
    third_party_user_id: str
    chat_type: str
    reminder_text: str
    timezone: str
    run_at: datetime | None
    cron_expr: str | None
    next_run_at: datetime | None
    status: ReminderScheduleStatus
    source_message_id: str
    source_message_time: datetime
    source_text: str
    last_triggered_at: datetime | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class ReminderJob:
    """提醒待执行实例。"""

    id: int | None
    schedule_id: int
    scheduled_for: datetime
    status: ReminderJobStatus
    lease_owner: str | None
    lease_until: datetime | None
    attempt_count: int
    available_at: datetime
    last_error: str | None
    dedupe_key: str
    sent_message_id: str | None
    sent_at: datetime | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class ReminderCreateCommand:
    """创建提醒时的结构化输入。"""

    user_id: str
    im_type: str
    chat_id: str
    third_party_user_id: str
    chat_type: str
    reminder_text: str
    source_message_id: str
    source_message_time: datetime
    source_text: str
    run_at: datetime | None = None
    cron_expr: str | None = None


@dataclass(frozen=True, slots=True)
class CreatedReminder:
    """创建提醒后的返回结果。"""

    schedule: ReminderSchedule
    first_job: ReminderJob | None


@dataclass(frozen=True, slots=True)
class ReminderExecutionBundle:
    """执行提醒时需要的规则与任务组合。"""

    schedule: ReminderSchedule
    job: ReminderJob


@dataclass(frozen=True, slots=True)
class ReminderConversationContext:
    """提醒文案生成使用的会话上下文。"""

    source_window_records: tuple[MemoryRecord, ...]
    latest_records: tuple[MemoryRecord, ...]
