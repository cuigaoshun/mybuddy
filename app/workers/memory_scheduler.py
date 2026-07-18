from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI

from app.agent.graph.memory_graph.state import MemoryGraphState
from app.storage.session_info_service import ChatSessionInfoService


@dataclass(slots=True)
class MemorySchedulerRunner:
    """统一管理长期记忆扫描调度器。"""

    scheduler: AsyncIOScheduler
    chat_session_info_service: ChatSessionInfoService
    memory_graph: Any

    @asynccontextmanager
    async def start(self, app: FastAPI):
        pass
        app.state.memory_scheduler = self
        self.scheduler.add_job(
            self.scan_pending_sessions,
            "interval",
            minutes=1,
            id="scan_pending_memory_sessions",
            replace_existing=True,
        )
        self.scheduler.start()
        try:
            yield
        finally:
            self.scheduler.shutdown(wait=False)

    def scan_pending_sessions(self) -> None:
        sessions = self.chat_session_info_service.list_sessions_pending_memory_processing(limit=20)
        for session in sessions:
            self.memory_graph.invoke(MemoryGraphState(session=session))
