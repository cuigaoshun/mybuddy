from __future__ import annotations


class WeixinApiError(Exception):
    def __init__(self, message: str, *, status: int, code: int | None = None, payload: object | None = None) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.payload = payload

    @property
    def is_session_expired(self) -> bool:
        return self.code == -14
