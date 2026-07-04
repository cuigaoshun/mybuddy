from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass, field

from fastapi import FastAPI
import lark_oapi as lark

from app.bootstrap.feishu import start_listener, stop_listener
from app.bootstrap.protocols import FeishuBootstrapContainer


@dataclass(slots=True)
class Listener:
    """统一管理应用内所有监听器。"""

    container: FeishuBootstrapContainer
    tasks: list[asyncio.Task[None]] = field(default_factory=list)
    feishu_client: lark.ws.Client | None = None

    @asynccontextmanager
    async def start(self, app: FastAPI):
        app.state.listener = self
        self.feishu_client = self.container.feishu_client()
        self.tasks.append(asyncio.create_task(start_listener(self.feishu_client)))
        try:
            yield
        finally:
            await self.stop()

    async def stop(self) -> None:
        if self.feishu_client is not None:
            await stop_listener(self.feishu_client)
        for task in self.tasks:
            if task.done():
                continue
            task.cancel()
        for task in self.tasks:
            try:
                await task
            except asyncio.CancelledError:
                pass
