from __future__ import annotations

from dataclasses import dataclass

from exa_py import Exa
from exa_py.api import Result
from loguru import logger

from app.core.config import ExaConfig


@dataclass(frozen=True, slots=True)
class WebSearchResult:
    title: str
    url: str
    snippet: str


class ExaWebSearchService:
    def __init__(self, config: ExaConfig) -> None:
        self._config: ExaConfig = config
        self._client: Exa = Exa(api_key=config.api_key)

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
        response_results: list[Result] = response.results
        results: list[WebSearchResult] = []
        for item in response_results:
            title = item.title.strip()
            url = item.url.strip()
            snippet = ""
            if item.highlights:
                for highlight in item.highlights:
                    normalized_highlight = highlight.strip()
                    if normalized_highlight != "":
                        snippet = normalized_highlight
                        break
            if title == "" and url == "":
                continue
            results.append(
                WebSearchResult(
                    title=title,
                    url=url,
                    snippet=snippet,
                )
            )
        return tuple(results)
