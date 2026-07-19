from __future__ import annotations

from contextlib import asynccontextmanager

from dependency_injector import providers
from dotenv import load_dotenv
from fastapi import FastAPI

from app.api.routes.health import router as health_router
from app.api.routes import wechat as wechat_routes
from app.api.routes.wechat import router as wechat_router
from app.bootstrap.container import AppContainer
from app.core.config import init_config
from app.event.bus import EventBus


@asynccontextmanager
async def lifespan(_: FastAPI):
    event_bus = EventBus()

    # 加载环境变量。
    load_dotenv()

    # 初始化项目配置。
    config = init_config()

    container = AppContainer()
    container.app_runtime_config.override(providers.Object(config.app))
    container.feishu_config.override(providers.Object(config.feishu))
    container.postgres_config.override(providers.Object(config.postgres))
    container.llm_config.override(providers.Object(config.llm))
    container.exa_config.override(providers.Object(config.exa))
    container.event_bus.override(providers.Object(event_bus))
    _.state.container = container
    container.wire(modules=[wechat_routes])

    # 初始化数据库 Engine。
    container.engine()

    # 预加载向量模型。
    container.embedding_provider()

    # 预编译 Agent Graph。
    container.agent_graph()

    # 预编译长期记忆处理图。
    container.memory_graph()

    # 装配并启动监听器；长期记忆调度器暂时停用。
    async with (
        container.listener().start(_),
        # container.memory_scheduler_runner().start(_),
    ):
        yield
    container.unwire()


# 创建并返回应用实例。
def create_app() -> FastAPI:
    app = FastAPI(lifespan=lifespan)
    app.include_router(health_router)
    app.include_router(wechat_router)
    return app
