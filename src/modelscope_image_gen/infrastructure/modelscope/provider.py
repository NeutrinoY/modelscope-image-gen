from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx

from modelscope_image_gen.application.provider_outcomes import (
    ProviderFailed,
    ProviderPending,
    ProviderRunning,
    ProviderSucceeded,
    ProviderTemporaryError,
    ProviderUnknownStatus,
    SubmitAccepted,
    SubmitRejected,
    SubmitUnknown,
)
from modelscope_image_gen.domain import (
    DomainError,
    ErrorCategory,
    ErrorCode,
    ErrorStage,
    GenerationRequest,
    ProviderImageReference,
    ProviderTaskReference,
)

_RETRYABLE = {408, 409, 425, 429, 500, 502, 503, 504}


class ModelScopeProvider:
    def __init__(
        self,
        *,
        client: httpx.AsyncClient,
        api_base: str,
        token: str,
        submit_timeout: float,
        status_timeout: float,
    ) -> None:
        self._client = client
        self._api_base = api_base.rstrip("/") + "/"
        self._token = token
        self._submit_timeout = submit_timeout
        self._status_timeout = status_timeout

    def validate(self, request: GenerationRequest) -> DomainError | None:
        now = datetime.now(UTC)
        if not self._token:
            return DomainError(
                code=ErrorCode.MODELSCOPE_TOKEN_MISSING,
                stage=ErrorStage.CONFIGURATION,
                category=ErrorCategory.CONFIGURATION,
                retryable=False,
                safe_message="MODELSCOPE_SDK_TOKEN is required to create or refresh ModelScope jobs.",
                occurred_at=now,
            )
        if not (64 <= request.size.width <= 1664 and 64 <= request.size.height <= 1664):
            return DomainError(
                code=ErrorCode.ARGUMENT_VALIDATION_FAILED,
                stage=ErrorStage.VALIDATION,
                category=ErrorCategory.VALIDATION,
                retryable=False,
                safe_message="The selected ModelScope model requires image dimensions between 64 and 1664 pixels.",
                occurred_at=now,
            )
        return None

    async def submit(self, request: GenerationRequest):
        validation = self.validate(request)
        if validation:
            return SubmitRejected(validation)
        payload: dict[str, Any] = {
            "model": request.model,
            "prompt": request.prompt,
            "size": request.size.as_modelscope_value(),
        }
        if request.negative_prompt is not None:
            payload["negative_prompt"] = request.negative_prompt
        if request.seed is not None:
            payload["seed"] = request.seed
        try:
            response = await self._client.post(
                f"{self._api_base}v1/images/generations",
                headers=self._submit_headers(),
                json=payload,
                timeout=self._submit_timeout,
            )
            response.raise_for_status()
            data = response.json()
            task_id = data.get("task_id") if isinstance(data, dict) else None
            request_id = response.headers.get("X-Request-Id")
            if not isinstance(task_id, str) or not task_id.strip():
                return SubmitUnknown(
                    DomainError(
                        code=ErrorCode.SUBMISSION_OUTCOME_UNKNOWN,
                        stage=ErrorStage.SUBMIT,
                        category=ErrorCategory.UPSTREAM_CONTRACT,
                        retryable=False,
                        possibly_submitted=True,
                        safe_message="ModelScope accepted the request but did not return a reliable task identifier.",
                        occurred_at=datetime.now(UTC),
                        provider_request_id=request_id,
                    )
                )
            return SubmitAccepted(task_id.strip(), request_id, "SUBMITTED")
        except httpx.HTTPStatusError as exc:
            response = exc.response
            retry_after = _retry_after(response.headers.get("Retry-After"))
            return SubmitRejected(
                DomainError(
                    code=ErrorCode.SUBMISSION_REJECTED,
                    stage=ErrorStage.SUBMIT,
                    category=ErrorCategory.UPSTREAM_HTTP,
                    retryable=response.status_code in _RETRYABLE,
                    retry_after_seconds=retry_after,
                    safe_message="ModelScope rejected the image generation request.",
                    occurred_at=datetime.now(UTC),
                    provider_request_id=response.headers.get("X-Request-Id"),
                )
            )
        except (httpx.RequestError, ValueError):
            return SubmitUnknown(
                DomainError(
                    code=ErrorCode.SUBMISSION_OUTCOME_UNKNOWN,
                    stage=ErrorStage.SUBMIT,
                    category=ErrorCategory.NETWORK,
                    retryable=False,
                    possibly_submitted=True,
                    safe_message=(
                        "The request may have reached ModelScope, but no reliable task identifier was recorded."
                    ),
                    occurred_at=datetime.now(UTC),
                )
            )

    async def check(self, task: ProviderTaskReference):
        if not self._token:
            raise ProviderTemporaryError(
                DomainError(
                    code=ErrorCode.MODELSCOPE_TOKEN_MISSING,
                    stage=ErrorStage.CONFIGURATION,
                    category=ErrorCategory.CONFIGURATION,
                    retryable=False,
                    safe_message="MODELSCOPE_SDK_TOKEN is required to refresh ModelScope jobs.",
                    occurred_at=datetime.now(UTC),
                )
            )
        try:
            response = await self._client.get(
                f"{self._api_base}v1/tasks/{task.task_id}",
                headers=self._status_headers(),
                timeout=self._status_timeout,
            )
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, dict):
                raise ValueError("response is not an object")
        except httpx.HTTPStatusError as exc:
            response = exc.response
            raise ProviderTemporaryError(
                DomainError(
                    code=ErrorCode.UPSTREAM_HTTP_ERROR,
                    stage=ErrorStage.STATUS_CHECK,
                    category=ErrorCategory.UPSTREAM_HTTP,
                    retryable=response.status_code in _RETRYABLE,
                    retry_after_seconds=_retry_after(response.headers.get("Retry-After")),
                    safe_message="The image generation status could not be refreshed.",
                    occurred_at=datetime.now(UTC),
                    provider_request_id=response.headers.get("X-Request-Id"),
                )
            ) from exc
        except httpx.RequestError as exc:
            raise ProviderTemporaryError(
                DomainError(
                    code=ErrorCode.NETWORK_ERROR,
                    stage=ErrorStage.STATUS_CHECK,
                    category=ErrorCategory.NETWORK,
                    retryable=True,
                    retry_after_seconds=1,
                    safe_message="The image generation status could not be refreshed because of a network error.",
                    occurred_at=datetime.now(UTC),
                )
            ) from exc
        except ValueError as exc:
            raise ProviderTemporaryError(
                DomainError(
                    code=ErrorCode.UPSTREAM_RESPONSE_INVALID,
                    stage=ErrorStage.STATUS_CHECK,
                    category=ErrorCategory.UPSTREAM_CONTRACT,
                    retryable=True,
                    safe_message="ModelScope returned an invalid status response.",
                    occurred_at=datetime.now(UTC),
                )
            ) from exc

        status = str(data.get("task_status") or "")
        request_id = response.headers.get("X-Request-Id")
        if status == "PENDING":
            return ProviderPending(request_id, status)
        if status in {"RUNNING", "PROCESSING"}:
            return ProviderRunning(request_id, status)
        if status == "SUCCEED":
            raw_images = data.get("output_images")
            references = tuple(
                ProviderImageReference(item, request_id) for item in raw_images or () if isinstance(item, str) and item
            )
            return ProviderSucceeded(references, request_id, status)
        if status == "FAILED":
            return ProviderFailed(
                DomainError(
                    code=ErrorCode.UPSTREAM_TASK_FAILED,
                    stage=ErrorStage.STATUS_CHECK,
                    category=ErrorCategory.UPSTREAM_TASK,
                    retryable=False,
                    safe_message="ModelScope reported that the image generation task failed.",
                    occurred_at=datetime.now(UTC),
                    provider_request_id=request_id,
                ),
                request_id,
                status,
            )
        error = DomainError(
            code=ErrorCode.UPSTREAM_STATUS_UNKNOWN,
            stage=ErrorStage.STATUS_CHECK,
            category=ErrorCategory.UPSTREAM_CONTRACT,
            retryable=True,
            retry_after_seconds=2,
            safe_message="ModelScope returned an unrecognized task status; the local job state was not changed.",
            occurred_at=datetime.now(UTC),
            provider_request_id=request_id,
        )
        return ProviderUnknownStatus(error, request_id, status)

    def _submit_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token}", "X-ModelScope-Async-Mode": "true"}

    def _status_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token}", "X-ModelScope-Task-Type": "image_generation"}


def _retry_after(value: str | None) -> int | None:
    try:
        parsed = int(value) if value is not None else None
        return parsed if parsed is not None and parsed >= 0 else None
    except ValueError:
        return None
