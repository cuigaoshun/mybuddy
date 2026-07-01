from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from app.api.routes.health import router as health_router
from app.bootstrap.feishu import start_feishu_bot_in_background

@asynccontextmanager
async def lifespan(_: FastAPI):
    start_feishu_bot_in_background(Path("config.toml"))
    yield


app = FastAPI(lifespan=lifespan)
app.include_router(health_router)
