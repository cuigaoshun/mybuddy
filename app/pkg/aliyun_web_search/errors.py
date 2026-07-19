from __future__ import annotations


class AliyunWebSearchError(Exception):
    def __init__(self, message: str, *, status: int, payload: object | None = None) -> None:
        super().__init__(message)
        self.status = status
        self.payload = payload
