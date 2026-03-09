# pyright: reportMissingImports=false
import asyncio
from unittest.mock import AsyncMock

import pytest
from service_test_helpers import DummyAsyncClient, FakeResponse

from modelscope_image_gen.config import Settings
from modelscope_image_gen.service import ImageGenerationService


@pytest.mark.asyncio
async def test_generate_image_returns_validation_error_when_api_key_missing() -> None:
    service = ImageGenerationService(Settings(modelscope_sdk_token=""))

    result = await service.generate_image(
        prompt="cat",
        model="Qwen/Qwen-Image",
        size="1024x1024",
        output_filename="x.jpg",
        output_dir="./outputs",
        poll_interval_seconds=None,
        max_poll_attempts=1,
        poll_backoff=False,
        max_poll_interval_seconds=1,
        negative_prompt=None,
        seed=None,
    )

    assert result.isError is True
    assert result.structuredContent is not None
    err = result.structuredContent["error"]
    assert err["reason_code"] == "MISSING_API_KEY"
    assert err["category"] == "validation"
    assert err["retryable"] is False


@pytest.mark.asyncio
async def test_generate_image_reports_missing_task_id(monkeypatch, tmp_path) -> None:
    service = ImageGenerationService(Settings(modelscope_sdk_token="token"))

    monkeypatch.setattr("modelscope_image_gen.services.workflows.generate.httpx.AsyncClient", DummyAsyncClient)

    async def fake_submit(client, **kwargs):
        return FakeResponse(status_code=200, headers={"X-Request-Id": "req-submit-1"}, json_data={"ok": True})

    monkeypatch.setattr(service.client, "submit_generation", AsyncMock(side_effect=fake_submit))

    result = await service.generate_image(
        prompt="cat",
        model="Qwen/Qwen-Image",
        size="1024x1024",
        output_filename="x.jpg",
        output_dir=str(tmp_path),
        poll_interval_seconds=None,
        max_poll_attempts=1,
        poll_backoff=False,
        max_poll_interval_seconds=1,
        negative_prompt=None,
        seed=None,
    )

    assert result.isError is True
    assert result.structuredContent is not None
    err = result.structuredContent["error"]
    assert err["reason_code"] == "TASK_ID_MISSING"
    assert err["category"] == "upstream_response"
    assert err["retryable"] is True


@pytest.mark.asyncio
async def test_generate_image_reports_task_failed(monkeypatch, tmp_path) -> None:
    service = ImageGenerationService(Settings(modelscope_sdk_token="token"))

    monkeypatch.setattr("modelscope_image_gen.services.workflows.generate.httpx.AsyncClient", DummyAsyncClient)

    async def fake_sleep(_):
        return None

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)

    async def fake_submit(client, **kwargs):
        return FakeResponse(status_code=200, headers={"X-Request-Id": "req-submit-2"}, json_data={"task_id": "task-1"})

    async def fake_poll(client, *, task_id):
        return FakeResponse(
            status_code=200,
            headers={"X-Request-Id": "req-poll-2"},
            json_data={"task_status": "FAILED", "message": "quota exceeded", "code": 429},
        )

    monkeypatch.setattr(service.client, "submit_generation", AsyncMock(side_effect=fake_submit))
    monkeypatch.setattr(service.client, "poll_task", AsyncMock(side_effect=fake_poll))

    result = await service.generate_image(
        prompt="cat",
        model="Qwen/Qwen-Image",
        size="1024x1024",
        output_filename="x.jpg",
        output_dir=str(tmp_path),
        poll_interval_seconds=0,
        max_poll_attempts=1,
        poll_backoff=False,
        max_poll_interval_seconds=1,
        negative_prompt=None,
        seed=None,
    )

    assert result.isError is True
    assert result.structuredContent is not None
    err = result.structuredContent["error"]
    assert err["reason_code"] == "TASK_FAILED"
    assert err["category"] == "upstream_task"
    assert err["retryable"] is True
    assert err["retry_after_seconds"] == 1


@pytest.mark.asyncio
async def test_generate_image_reports_unknown_task_status(monkeypatch, tmp_path) -> None:
    service = ImageGenerationService(Settings(modelscope_sdk_token="token"))

    monkeypatch.setattr("modelscope_image_gen.services.workflows.generate.httpx.AsyncClient", DummyAsyncClient)

    async def fake_sleep(_):
        return None

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)

    async def fake_submit(client, **kwargs):
        return FakeResponse(status_code=200, headers={"X-Request-Id": "req-submit-3"}, json_data={"task_id": "task-2"})

    async def fake_poll(client, *, task_id):
        return FakeResponse(status_code=200, headers={"X-Request-Id": "req-poll-3"}, json_data={"task_status": "CANCELLED"})

    monkeypatch.setattr(service.client, "submit_generation", AsyncMock(side_effect=fake_submit))
    monkeypatch.setattr(service.client, "poll_task", AsyncMock(side_effect=fake_poll))

    result = await service.generate_image(
        prompt="cat",
        model="Qwen/Qwen-Image",
        size="1024x1024",
        output_filename="x.jpg",
        output_dir=str(tmp_path),
        poll_interval_seconds=0,
        max_poll_attempts=1,
        poll_backoff=False,
        max_poll_interval_seconds=1,
        negative_prompt=None,
        seed=None,
    )

    assert result.isError is True
    assert result.structuredContent is not None
    err = result.structuredContent["error"]
    assert err["reason_code"] == "UNKNOWN_TASK_STATUS"
    assert err["category"] == "upstream_response"
    assert err["retryable"] is False


@pytest.mark.asyncio
async def test_generate_image_redacts_sensitive_fields_in_body(monkeypatch) -> None:
    service = ImageGenerationService(Settings(modelscope_sdk_token="token"))

    monkeypatch.setattr("modelscope_image_gen.services.workflows.generate.httpx.AsyncClient", DummyAsyncClient)

    async def fake_submit(client, **kwargs):
        return FakeResponse(
            status_code=200,
            headers={"X-Request-Id": "req-submit-4"},
            json_data={"error": "bad", "token": "abc123", "nested": {"authorization": "Bearer SECRET_TOKEN"}},
        )

    monkeypatch.setattr(service.client, "submit_generation", AsyncMock(side_effect=fake_submit))

    result = await service.generate_image(
        prompt="cat",
        model="Qwen/Qwen-Image",
        size="1024x1024",
        output_filename="x.jpg",
        output_dir="./outputs",
        poll_interval_seconds=0,
        max_poll_attempts=1,
        poll_backoff=False,
        max_poll_interval_seconds=1,
        negative_prompt=None,
        seed=None,
    )

    assert result.structuredContent is not None
    err = result.structuredContent["error"]
    assert err["body"]["token"] == "[REDACTED]"
    assert err["body"]["nested"]["authorization"] == "[REDACTED]"
