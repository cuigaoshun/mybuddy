from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse

from exa_py import Exa
from loguru import logger

from app.core.config import ExaConfig


@dataclass(frozen=True, slots=True)
class WebSearchResult:
    title: str
    url: str
    snippet: str
    domain: str


class ExaWebSearchService:
    def __init__(self, config: ExaConfig) -> None:
        self._config: ExaConfig = config
        self._client: Exa = Exa(api_key=config.api_key)

    def is_available(self) -> bool:
        return True

    def search(self, query: str, limit: int | None = None) -> tuple[WebSearchResult, ...]:
        normalized_query = query.strip()
        if normalized_query == "":
            return ()

        resolved_limit = limit if limit is not None and limit > 0 else self._config.default_limit
        try:
            response = self._client.search(
                normalized_query,
                type="auto",
                num_results=resolved_limit,
            )
        except Exception as error:
            logger.exception("exa 搜索失败，query={} error={}", normalized_query, error)
            return ()
        response_results = response.results
        results: list[WebSearchResult] = []
        for item in response_results:
            title = _read_result_field(item, "title")
            url = _read_result_field(item, "url")
            snippet = _read_exa_snippet(item)
            domain = _extract_domain(url)
            if title == "" and url == "":
                continue
            results.append(
                WebSearchResult(
                    title=title,
                    url=url,
                    snippet=snippet,
                    domain=domain,
                )
            )
        return tuple(results)


def _read_result_field(item: object, field_name: str) -> str:
    value = getattr(item, field_name)
    return value.strip() if isinstance(value, str) else ""


def _read_exa_snippet(item: object) -> str:
    highlights = item.highlights
    if isinstance(highlights, list):
        for highlight in highlights:
            if isinstance(highlight, str):
                normalized_highlight = highlight.strip()
                if normalized_highlight != "":
                    return normalized_highlight
    text = item.text
    return text.strip() if isinstance(text, str) else ""


def _extract_domain(url: str) -> str:
    normalized_url = url.strip()
    if normalized_url == "":
        return ""
    return urlparse(normalized_url).netloc
