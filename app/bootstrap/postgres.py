from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from app.core.config import PostgresConfig

_engine: Engine | None = None


def get_engine(config: PostgresConfig) -> Engine:
    """按应用级单例方式创建并复用 SQLAlchemy Engine。"""
    global _engine

    if _engine is None:
        password_part = config.password
        _engine = create_engine(
            (
                f"postgresql+psycopg://{config.user}:{password_part}@{config.host}:{config.port}/"
                f"{config.database}?connect_timeout={config.connect_timeout_seconds}"
            ),
            future=True,
        )

    return _engine
