from __future__ import annotations

from dataclasses import dataclass

from loguru import logger

from app.core.config import WebSearchConfig
from app.pkg.aliyun_web_search import Client, Config, GetWebSearchRequest


@dataclass(frozen=True, slots=True)
class WebSearchResult:
    title: str
    url: str
    snippet: str


class WebSearchService:
    def __init__(self, config: WebSearchConfig) -> None:
        self._config: WebSearchConfig = config
        self._client: Client = Client(
            config=Config(
                bearer_token=config.api_key,
                endpoint=config.endpoint,
                protocol=config.protocol,
            )
        )

    def search(self, query: str, limit: int | None = None) -> tuple[WebSearchResult, ...]:
        normalized_query = query.strip()
        if normalized_query == "":
            return ()

        resolved_limit = limit if limit is not None and limit > 0 else self._config.default_limit
        try:
            response = self._client.get_web_search(
                self._config.workspace,
                self._config.service_id,
                GetWebSearchRequest(
                    query=normalized_query,
                    top_k=resolved_limit,
                    query_rewrite=self._config.query_rewrite,
                    content_type=self._config.content_type,
                ),
            )
        except Exception as error:
            logger.exception("阿里云联网搜索失败，query={} error={}", normalized_query, error)
            return ()

        response_body = response.body
        response_result = response_body.result
        response_results = response_result.search_result
        if response_results is None:
            return ()

        results: list[WebSearchResult] = []
        for item in response_results:
            title = _normalize_text(item.title)
            url = _normalize_text(item.link)
            snippet = _normalize_text(item.snippet)
            if snippet == "":
                snippet = _normalize_text(item.content)[:200]
            if title == "" or url == "" or snippet == "":
                continue
            results.append(
                WebSearchResult(
                    title=title,
                    url=url,
                    snippet=snippet,
                )
            )
        return tuple(results)


def _normalize_text(value: object) -> str:
    if isinstance(value, str):
        return value.strip()
    return ""
