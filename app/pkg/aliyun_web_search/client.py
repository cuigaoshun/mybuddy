from __future__ import annotations

from urllib.parse import urljoin

import httpx

from .errors import AliyunWebSearchError
from .models import Config, GetWebSearchRequest, GetWebSearchResponse, GetWebSearchResponseBody


class Client:
    def __init__(self, config: Config) -> None:
        self._config = config

    def get_web_search(
        self,
        workspace_name: str,
        service_id: str,
        request: GetWebSearchRequest,
    ) -> GetWebSearchResponse:
        endpoint = self._config.endpoint.strip()
        if endpoint == "":
            raise AliyunWebSearchError("阿里云联网搜索 endpoint 不能为空", status=500)

        base_url = f"{self._config.protocol}://{endpoint}/"
        path = f"v3/openapi/workspaces/{workspace_name}/web-search/{service_id}"
        http_request = httpx.Request(
            method="POST",
            url=urljoin(base_url, path),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._config.bearer_token}",
            },
            json=request.to_map(),
        )
        try:
            with httpx.Client(timeout=30) as client:
                response = client.send(http_request)
        except httpx.HTTPError as exc:
            raise AliyunWebSearchError(str(exc), status=500) from exc
        except Exception as exc:
            raise AliyunWebSearchError(str(exc), status=500) from exc

        try:
            payload = response.json() if response.content else {}
        except ValueError as exc:
            raise AliyunWebSearchError("阿里云联网搜索响应不是合法 JSON", status=response.status_code) from exc

        if not isinstance(payload, dict):
            raise AliyunWebSearchError("阿里云联网搜索响应不是合法 JSON 对象", status=response.status_code, payload=payload)

        response_body = GetWebSearchResponseBody.from_map(payload)
        if response.status_code < 200 or response.status_code >= 300:
            raise AliyunWebSearchError(
                response_body.message or f"HTTP {response.status_code}",
                status=response.status_code,
                payload=payload,
            )
        if response_body.code:
            raise AliyunWebSearchError(
                response_body.message or response_body.code,
                status=response.status_code,
                payload=payload,
            )

        return GetWebSearchResponse(
            status_code=response.status_code,
            headers=dict(response.headers),
            body=response_body,
        )
