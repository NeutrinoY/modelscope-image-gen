import json

import httpx
import pytest

from modelscope_image_gen.application.provider_outcomes import (
    ProviderImageError,
    ProviderSucceeded,
    ProviderTemporaryError,
    ProviderUnknownStatus,
    SubmitAccepted,
)
from modelscope_image_gen.domain import GenerationRequest, ImageSize, ProviderImageReference, ProviderTaskReference
from modelscope_image_gen.infrastructure.modelscope.provider import ModelScopeProvider


@pytest.mark.anyio
async def test_modelscope_submit_and_multi_image_status_mapping() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/v1/images/generations"):
            body = json.loads(request.content)
            assert body["size"] == "1024x768"
            assert request.headers["X-ModelScope-Async-Mode"] == "true"
            return httpx.Response(200, json={"task_id": "task"}, headers={"X-Request-Id": "submit-req"})
        return httpx.Response(
            200,
            json={"task_status": "SUCCEED", "output_images": ["https://signed/1", "https://signed/2"]},
            headers={"X-Request-Id": "status-req"},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = ModelScopeProvider(
            client=client,
            api_base="https://api.example/",
            token="token",
            submit_timeout=2,
            status_timeout=2,
            download_timeout=2,
        )
        submitted = await provider.submit(GenerationRequest(prompt="cat", model="m", size=ImageSize(1024, 768)))
        checked = await provider.check(ProviderTaskReference("task"))

    assert isinstance(submitted, SubmitAccepted)
    assert submitted.task_id == "task"
    assert isinstance(checked, ProviderSucceeded)
    assert len(checked.references) == 2


@pytest.mark.anyio
async def test_unknown_status_is_closed_outcome_not_job_failure() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"task_status": "NEW_FUTURE_STATUS"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = ModelScopeProvider(
            client=client,
            api_base="https://api.example/",
            token="token",
            submit_timeout=2,
            status_timeout=2,
            download_timeout=2,
        )
        outcome = await provider.check(ProviderTaskReference("task"))

    assert isinstance(outcome, ProviderUnknownStatus)
    assert outcome.error.code.value == "UPSTREAM_STATUS_UNKNOWN"


@pytest.mark.anyio
async def test_success_rejects_non_list_output_images() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"task_status": "SUCCEED", "output_images": "https://signed/image"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = ModelScopeProvider(
            client=client,
            api_base="https://api.example/",
            token="token",
            submit_timeout=2,
            status_timeout=2,
            download_timeout=2,
        )
        with pytest.raises(ProviderTemporaryError) as raised:
            await provider.check(ProviderTaskReference("task"))

    assert raised.value.error.code.value == "UPSTREAM_RESPONSE_INVALID"


@pytest.mark.anyio
async def test_provider_validates_seed_range_before_submit() -> None:
    async with httpx.AsyncClient() as client:
        provider = ModelScopeProvider(
            client=client,
            api_base="https://api.example/",
            token="token",
            submit_timeout=2,
            status_timeout=2,
            download_timeout=2,
        )
        error = provider.validate(GenerationRequest(prompt="cat", model="m", seed=2**31))

    assert error is not None
    assert error.code.value == "ARGUMENT_VALIDATION_FAILED"


@pytest.mark.anyio
async def test_provider_owns_image_download_and_maps_http_failures() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, headers={"Retry-After": "4", "X-Request-Id": "download-req"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = ModelScopeProvider(
            client=client,
            api_base="https://api.example/",
            token="token",
            submit_timeout=2,
            status_timeout=2,
            download_timeout=2,
        )
        with pytest.raises(ProviderImageError) as raised:
            async with provider.open_image(ProviderImageReference("https://signed/image")):
                pass

    assert raised.value.error.code.value == "DOWNLOAD_FAILED"
    assert raised.value.error.retry_after_seconds == 4
    assert raised.value.error.provider_request_id == "download-req"
