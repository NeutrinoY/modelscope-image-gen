from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

import httpx

from modelscope_image_gen.application.provider_outcomes import ProviderImageError
from modelscope_image_gen.domain import (
    DomainError,
    ErrorCategory,
    ErrorCode,
    ErrorStage,
    ProviderImageReference,
)

from .http_mapping import RETRYABLE_STATUS_CODES, retry_after_seconds


class ModelScopeImageDownloader:
    def __init__(self, client: httpx.AsyncClient, timeout: float) -> None:
        self._client = client
        self._timeout = timeout

    @asynccontextmanager
    async def open(self, reference: ProviderImageReference) -> AsyncIterator[HttpxImageStream]:
        try:
            async with self._client.stream("GET", reference.locator, timeout=self._timeout) as response:
                response.raise_for_status()
                yield HttpxImageStream(response, _content_length(response.headers.get("Content-Length")))
        except httpx.HTTPStatusError as exc:
            response = exc.response
            raise ProviderImageError(
                DomainError(
                    code=ErrorCode.DOWNLOAD_FAILED,
                    stage=ErrorStage.DOWNLOAD,
                    category=ErrorCategory.UPSTREAM_HTTP,
                    retryable=response.status_code in RETRYABLE_STATUS_CODES,
                    retry_after_seconds=retry_after_seconds(response.headers.get("Retry-After")),
                    safe_message="The image artifact could not be downloaded from ModelScope.",
                    occurred_at=datetime.now(UTC),
                    provider_request_id=response.headers.get("X-Request-Id"),
                )
            ) from exc
        except httpx.RequestError as exc:
            raise ProviderImageError(
                DomainError(
                    code=ErrorCode.DOWNLOAD_FAILED,
                    stage=ErrorStage.DOWNLOAD,
                    category=ErrorCategory.NETWORK,
                    retryable=True,
                    retry_after_seconds=1,
                    safe_message="The image artifact could not be downloaded because of a network error.",
                    occurred_at=datetime.now(UTC),
                )
            ) from exc


class HttpxImageStream:
    def __init__(self, response: httpx.Response, content_length: int | None) -> None:
        self._response = response
        self.content_length = content_length

    def __aiter__(self) -> AsyncIterator[bytes]:
        return self._response.aiter_bytes()


def _content_length(value: str | None) -> int | None:
    try:
        parsed = int(value) if value is not None else None
        return parsed if parsed is not None and parsed >= 0 else None
    except ValueError:
        return None
