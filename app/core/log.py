from __future__ import annotations

import logging
from pathlib import Path
import sys

from loguru import logger


class InterceptHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        logger.opt(exception=record.exc_info, depth=6).log(level, record.getMessage())


def configure_logging(log_level: str, log_dir: str) -> None:
    """Configure the process logging level for the demo bot."""
    log_directory = Path(log_dir)
    log_file_path = log_directory / "mybuddy.log"
    log_directory.mkdir(parents=True, exist_ok=True)

    logger.remove()
    logger.add(
        sys.stderr,
        level=_resolve_logging_level(log_level),
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level} | {name}:{function}:{line} - {message}",
    )
    logger.add(
        log_file_path,
        level=_resolve_logging_level(log_level),
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level} | {name}:{function}:{line} - {message}",
        rotation="00:00",
        retention="7 days",
        encoding="utf-8",
    )

    logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)


def _resolve_logging_level(log_level: str) -> str:
    normalized_level = log_level.upper()
    if normalized_level == "DEBUG":
        return "DEBUG"
    if normalized_level == "WARNING":
        return "WARNING"
    if normalized_level == "ERROR":
        return "ERROR"
    return "INFO"
