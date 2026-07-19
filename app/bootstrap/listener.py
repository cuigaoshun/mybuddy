from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any

from fastapi import FastAPI
import lark_oapi as lark

from app.bootstrap.feishu import start_listener, stop_listener
from app.bootstrap.protocols import AppBootstrapContainer


@dataclass(slots=True)
class Listener:
    """统一管理应用内所有监听器。"""

    container: AppBootstrapContainer
    tasks: list[asyncio.Task[None]] = field(default_factory=list)
    feishu_client: lark.ws.Client | None = None
    wechat_poller_runner: Any | None = None

    @asynccontextmanager
    async def start(self, app: FastAPI):
        # 把 listener 挂到应用状态，便于运行时排查或扩展生命周期控制。
        app.state.listener = self
        self.feishu_client = self.container.feishu_client()
        self.wechat_poller_runner = self.container.wechat_poller_runner()
        # 飞书 websocket 监听和微信长轮询 runner 一起纳入统一生命周期管理。
        self.tasks.append(asyncio.create_task(start_listener(self.feishu_client)))
        async with self.wechat_poller_runner.start(app):
            try:
                yield
            finally:
                await self.stop()

    async def stop(self) -> None:
        # 先关闭飞书 client，再回收统一 listener 挂着的异步任务。
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
