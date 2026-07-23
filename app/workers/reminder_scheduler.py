from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI
from loguru import logger

from app.services.reminder_execution import ReminderExecutionService
from app.storage.reminder_service import ReminderService

REMINDER_POLL_INTERVAL_SECONDS = 30


@dataclass(slots=True)
class ReminderSchedulerRunner:
    """统一管理 reminder 调度器。"""

    scheduler: AsyncIOScheduler
    reminder_service: ReminderService
    reminder_execution_service: ReminderExecutionService

    @asynccontextmanager
    async def start(self, app: FastAPI):
        app.state.reminder_scheduler = self
        self.scheduler.add_job(
            self.scan_due_reminders,
            "interval",
            seconds=REMINDER_POLL_INTERVAL_SECONDS,
            id="scan_due_reminders",
            replace_existing=True,
        )
        self.scheduler.start()
        try:
            yield
        finally:
            self.scheduler.shutdown(wait=False)

    def scan_due_reminders(self) -> None:
        now = datetime.now(UTC)
        self.reminder_service.materialize_due_recurring_jobs(now=now)
        job_ids = self.reminder_service.claim_due_jobs(now=now)
        for job_id in job_ids:
            try:  # noqa: BROAD_EXCEPT_OK
                self.reminder_execution_service.execute_job(job_id)
            except Exception:  # noqa: BROAD_EXCEPT_OK
                logger.exception("执行 reminder job 失败，job_id={job_id}", job_id=job_id)
