from __future__ import annotations

import logging


def configure_logging(log_level: str) -> None:
    """Configure the process logging level for the demo bot."""
    logging.basicConfig(
        level=_resolve_logging_level(log_level),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def _resolve_logging_level(log_level: str) -> int:
    normalized_level = log_level.upper()
    if normalized_level == "DEBUG":
        return logging.DEBUG
    if normalized_level == "WARNING":
        return logging.WARNING
    if normalized_level == "ERROR":
        return logging.ERROR
    return logging.INFO
