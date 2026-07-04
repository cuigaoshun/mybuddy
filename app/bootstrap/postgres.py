from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from app.core.config import PostgresConfig


def get_engine(config: PostgresConfig) -> Engine:
    """根据 PostgreSQL 配置创建 SQLAlchemy Engine，单例交给容器管理。"""
    password_part = config.password
    return create_engine(
        (
            f"postgresql+psycopg://{config.user}:{password_part}@{config.host}:{config.port}/"
            f"{config.database}?connect_timeout={config.connect_timeout_seconds}"
        ),
        future=True,
    )
