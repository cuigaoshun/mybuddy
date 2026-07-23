from __future__ import annotations

from datetime import datetime
from typing import Protocol

from app.storage.reminder_models import CreatedReminder, ReminderExecutionBundle, ReminderJob, ReminderSchedule


class ReminderRepository(Protocol):
    """提醒规则与执行任务仓储协议。"""

    def create_schedule(self, schedule: ReminderSchedule) -> ReminderSchedule:
        ...

    def create_job(self, job: ReminderJob) -> ReminderJob:
        ...

    def materialize_due_recurring_jobs(self, now: datetime, limit: int) -> tuple[int, ...]:
        ...

    def claim_due_jobs(self, now: datetime, lease_owner: str, lease_until: datetime, limit: int) -> tuple[int, ...]:
        ...

    def get_execution_bundle(self, job_id: int) -> ReminderExecutionBundle | None:
        ...

    def mark_job_sent(self, job_id: int, sent_message_id: str, sent_at: datetime) -> None:
        ...

    def mark_job_retryable(self, job_id: int, available_at: datetime, last_error: str) -> None:
        ...

    def mark_job_blocked_user_route(self, job_id: int, available_at: datetime, last_error: str) -> None:
        ...

    def mark_job_failed(self, job_id: int, last_error: str) -> None:
        ...
