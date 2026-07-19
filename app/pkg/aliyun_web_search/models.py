from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class Config:
    bearer_token: str
    endpoint: str
    protocol: str = "http"


@dataclass(frozen=True, slots=True)
class GetWebSearchRequestHistory:
    content: str
    role: str

    def to_map(self) -> dict[str, str]:
        return {
            "content": self.content,
            "role": self.role,
        }


@dataclass(frozen=True, slots=True)
class GetWebSearchRequest:
    query: str
    content_type: str | None = None
    history: tuple[GetWebSearchRequestHistory, ...] = ()
    query_rewrite: bool | None = None
    top_k: int | None = None

    def to_map(self) -> dict[str, object]:
        result: dict[str, object] = {"query": self.query}
        if self.content_type is not None:
            result["content_type"] = self.content_type
        if self.history:
            result["history"] = [item.to_map() for item in self.history]
        if self.query_rewrite is not None:
            result["query_rewrite"] = self.query_rewrite
        if self.top_k is not None:
            result["top_k"] = self.top_k
        return result


@dataclass(frozen=True, slots=True)
class GetWebSearchResponseBodyResultSearchResult:
    title: str | None = None
    link: str | None = None
    snippet: str | None = None
    content: str | None = None
    position: int | None = None
    meta_info: dict[str, object] = field(default_factory=dict)

    @classmethod
    def from_map(cls, payload: object) -> "GetWebSearchResponseBodyResultSearchResult":
        if not isinstance(payload, dict):
            return cls()
        raw_title = payload.get("title")
        if not isinstance(raw_title, str):
            raw_title = payload.get("tilte")
        raw_link = payload.get("link")
        raw_snippet = payload.get("snippet")
        raw_content = payload.get("content")
        raw_position = payload.get("position")
        raw_meta_info = payload.get("meta_info")
        return cls(
            title=raw_title if isinstance(raw_title, str) else None,
            link=raw_link if isinstance(raw_link, str) else None,
            snippet=raw_snippet if isinstance(raw_snippet, str) else None,
            content=raw_content if isinstance(raw_content, str) else None,
            position=raw_position if isinstance(raw_position, int) else None,
            meta_info=raw_meta_info if isinstance(raw_meta_info, dict) else {},
        )


@dataclass(frozen=True, slots=True)
class GetWebSearchResponseBodyResult:
    search_result: tuple[GetWebSearchResponseBodyResultSearchResult, ...] = ()

    @classmethod
    def from_map(cls, payload: object) -> "GetWebSearchResponseBodyResult":
        if not isinstance(payload, dict):
            return cls()
        raw_search_result = payload.get("search_result")
        if not isinstance(raw_search_result, list):
            return cls()
        return cls(
            search_result=tuple(GetWebSearchResponseBodyResultSearchResult.from_map(item) for item in raw_search_result),
        )


@dataclass(frozen=True, slots=True)
class GetWebSearchResponseBody:
    request_id: str | None = None
    latency: int | float | None = None
    code: str | None = None
    message: str | None = None
    result: GetWebSearchResponseBodyResult = field(default_factory=GetWebSearchResponseBodyResult)

    @classmethod
    def from_map(cls, payload: object) -> "GetWebSearchResponseBody":
        if not isinstance(payload, dict):
            return cls()
        raw_request_id = payload.get("request_id")
        raw_latency = payload.get("latency")
        raw_code = payload.get("code")
        raw_message = payload.get("message")
        return cls(
            request_id=raw_request_id if isinstance(raw_request_id, str) else None,
            latency=raw_latency if isinstance(raw_latency, int | float) else None,
            code=raw_code if isinstance(raw_code, str) else None,
            message=raw_message if isinstance(raw_message, str) else None,
            result=GetWebSearchResponseBodyResult.from_map(payload.get("result")),
        )


@dataclass(frozen=True, slots=True)
class GetWebSearchResponse:
    status_code: int
    headers: dict[str, str]
    body: GetWebSearchResponseBody
