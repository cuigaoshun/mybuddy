from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse
from typing import Protocol, cast

from exa_py import Exa
from loguru import logger

from app.core.config import ExaConfig


class ExaSearchClient(Protocol):
    def search(self, query: str, *, type: str, num_results: int, contents: dict[str, bool]) -> object:
        ...


@dataclass(frozen=True, slots=True)
class WebSearchResult:
    title: str
    url: str
    snippet: str
    domain: str
    rank: int | None


class ExaWebSearchService:
    def __init__(self, config: ExaConfig) -> None:
        self._config: ExaConfig = config
        self._client: ExaSearchClient | None = (
            cast(ExaSearchClient, Exa(api_key=config.api_key)) if config.api_key else None
        )

    def is_available(self) -> bool:
        return self._client is not None

    def search(self, query: str, limit: int | None = None) -> tuple[WebSearchResult, ...]:
        normalized_query = query.strip()
        if normalized_query == "":
            return ()
        if self._client is None:
            logger.warning("exa 未配置 api_key，跳过 web 搜索")
            return ()

        resolved_limit = limit if limit is not None and limit > 0 else self._config.default_limit
        try:
            response = self._client.search(
                normalized_query,
                type="auto",
                num_results=resolved_limit,
                contents={"highlights": True},
            )
        except Exception as error:
            logger.exception("exa 搜索失败，query={} error={}", normalized_query, error)
            return ()
        response_results = getattr(response, "results", ())
        results: list[WebSearchResult] = []
        for item in response_results:
            title = _read_result_field(item, "title")
            url = _read_result_field(item, "url")
            snippet = _read_exa_snippet(item)
            domain = _extract_domain(url)
            rank = _read_result_rank(item)
            if title == "" and url == "":
                continue
            results.append(
                WebSearchResult(
                    title=title,
                    url=url,
                    snippet=snippet,
                    domain=domain,
                    rank=rank,
                )
            )
        return tuple(results)


def _read_result_field(item: object, field_name: str) -> str:
    if isinstance(item, dict):
        value = item.get(field_name)
    else:
        value = getattr(item, field_name, None)
    return value.strip() if isinstance(value, str) else ""


def _read_result_rank(item: object) -> int | None:
    if isinstance(item, dict):
        value = item.get("rank")
    else:
        value = getattr(item, "rank", None)
    return value if isinstance(value, int) else None


def _read_exa_snippet(item: object) -> str:
    highlights = getattr(item, "highlights", None)
    if isinstance(highlights, list):
        for highlight in highlights:
            if isinstance(highlight, str):
                normalized_highlight = highlight.strip()
                if normalized_highlight != "":
                    return normalized_highlight
    text = getattr(item, "text", None)
    return text.strip() if isinstance(text, str) else ""


def _extract_domain(url: str) -> str:
    normalized_url = url.strip()
    if normalized_url == "":
        return ""
    return urlparse(normalized_url).netloc
