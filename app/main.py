from __future__ import annotations

from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI

from app.api.routes.health import router as health_router
from app.bootstrap.feishu import start_feishu_bot_in_background
from app.core.config import init_config


@asynccontextmanager
async def lifespan(_: FastAPI):
    start_feishu_bot_in_background()
    yield


load_dotenv()
init_config()
app = FastAPI(lifespan=lifespan)
app.include_router(health_router)
