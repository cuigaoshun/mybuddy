from __future__ import annotations

from pathlib import Path
from typing import Final

from dynaconf import Dynaconf
from pydantic import BaseModel, ConfigDict, Field, field_validator

DEFAULT_CONFIG_PATH: Final[Path] = Path("config.toml")


class FeishuConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    app_id: str = Field(min_length=1)
    app_secret: str = Field(min_length=1)
    log_level: str = "INFO"
    log_dir: str = "logs"

    @field_validator("app_id", "app_secret", "log_level", "log_dir", mode="before")
    @classmethod
    def strip_string_value(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator("app_id", "app_secret")
    @classmethod
    def validate_required_value(cls, value: str) -> str:
        if value == "":
            raise ValueError("不能为空")
        return value


class AppConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    feishu: FeishuConfig


config: AppConfig | None = None


def load_config(config_path: Path) -> AppConfig:
    """Load config via Dynaconf, allowing env vars to override file values."""
    settings = Dynaconf(
        settings_files=[str(config_path)],
        envvar_prefix="MYBUDDY",
    )

    return AppConfig(
        feishu=FeishuConfig(
            app_id=settings.get("feishu.app_id"),
            app_secret=settings.get("feishu.app_secret"),
            log_level=settings.get("feishu.log_level", "INFO"),
            log_dir=settings.get("feishu.log_dir", "logs"),
        ),
    )


def init_config(config_path: Path = DEFAULT_CONFIG_PATH) -> AppConfig:
    global config
    config = load_config(config_path)
    return config


def get_config() -> AppConfig:
    if config is None:
        return init_config()
    return config
