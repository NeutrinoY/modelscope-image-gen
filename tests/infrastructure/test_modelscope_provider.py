import json

import httpx
import pytest

from modelscope_image_gen.application.provider_outcomes import (
    ProviderSucceeded,
    ProviderUnknownStatus,
    SubmitAccepted,
)
from modelscope_image_gen.domain import GenerationRequest, ImageSize, ProviderTaskReference
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
            client=client, api_base="https://api.example/", token="token", submit_timeout=2, status_timeout=2
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
            client=client, api_base="https://api.example/", token="token", submit_timeout=2, status_timeout=2
        )
        outcome = await provider.check(ProviderTaskReference("task"))

    assert isinstance(outcome, ProviderUnknownStatus)
    assert outcome.error.code.value == "UPSTREAM_STATUS_UNKNOWN"
