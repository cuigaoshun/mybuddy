from __future__ import annotations

from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI

from app.api.routes.health import router as health_router
from app.bootstrap.feishu import start_feishu_bot_in_background
from app.bootstrap.postgres import get_engine
from app.core.config import init_config
from app.event.bus import EventBus
from app.memory.embeddings import SentenceTransformerEmbeddingProvider


@asynccontextmanager
async def lifespan(_: FastAPI):
    event_bus = EventBus()

    # 加载环境变量。
    load_dotenv()

    # 初始化项目配置。
    config = init_config()

    # 初始化数据库 Engine。
    get_engine(config.postgres)

    # 预加载向量模型。
    SentenceTransformerEmbeddingProvider()

    # 启动飞书后台线程。
    start_feishu_bot_in_background(event_bus)
    yield


# 创建并返回应用实例。
def create_app() -> FastAPI:
    app = FastAPI(lifespan=lifespan)
    app.include_router(health_router)
    return app
