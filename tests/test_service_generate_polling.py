# pyright: reportMissingImports=false
import asyncio
from unittest.mock import AsyncMock

import pytest
from service_test_helpers import DummyAsyncClient, FakeResponse

from modelscope_image_gen.config import Settings
from modelscope_image_gen.service import ImageGenerationService


@pytest.mark.asyncio
async def test_generate_image_timeout_uses_backoff_schedule(monkeypatch, tmp_path) -> None:
    service = ImageGenerationService(Settings(modelscope_sdk_token="token"))

    monkeypatch.setattr("modelscope_image_gen.services.workflows.generate.httpx.AsyncClient", DummyAsyncClient)

    waits: list[float] = []

    async def fake_sleep(seconds):
        waits.append(seconds)
        return None

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)

    async def fake_submit(client, **kwargs):
        return FakeResponse(status_code=200, headers={"X-Request-Id": "req-submit-timeout"}, json_data={"task_id": "task-timeout"})

    async def fake_poll(client, *, task_id):
        return FakeResponse(status_code=200, headers={"X-Request-Id": "req-poll-timeout"}, json_data={"task_status": "RUNNING"})

    monkeypatch.setattr(service.client, "submit_generation", AsyncMock(side_effect=fake_submit))
    monkeypatch.setattr(service.client, "poll_task", AsyncMock(side_effect=fake_poll))

    result = await service.generate_image(
        prompt="cat",
        model="Qwen/Qwen-Image",
        size="1024x1024",
        output_filename="x.jpg",
        output_dir=str(tmp_path),
        poll_interval_seconds=1,
        max_poll_attempts=3,
        poll_backoff=True,
        max_poll_interval_seconds=3,
        negative_prompt=None,
        seed=None,
    )

    assert result.isError is True
    assert result.structuredContent is not None
    err = result.structuredContent["error"]
    assert err["reason_code"] == "POLL_TIMEOUT"
    assert waits == [1, 2, 3]


@pytest.mark.asyncio
async def test_generate_image_treats_processing_as_in_progress(monkeypatch, tmp_path) -> None:
    service = ImageGenerationService(Settings(modelscope_sdk_token="token"))

    monkeypatch.setattr("modelscope_image_gen.services.workflows.generate.httpx.AsyncClient", DummyAsyncClient)

    waits: list[float] = []

    async def fake_sleep(seconds):
        waits.append(seconds)
        return None

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)

    async def fake_submit(client, **kwargs):
        return FakeResponse(status_code=200, headers={"X-Request-Id": "req-submit-processing"}, json_data={"task_id": "task-processing"})

    async def fake_poll(client, *, task_id):
        return FakeResponse(
            status_code=200,
            headers={"X-Request-Id": "req-poll-processing"},
            json_data={"task_status": "PROCESSING", "outputs": {}},
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
        max_poll_attempts=2,
        poll_backoff=False,
        max_poll_interval_seconds=1,
        negative_prompt=None,
        seed=None,
    )

    assert result.isError is True
    assert result.structuredContent is not None
    err = result.structuredContent["error"]
    assert err["reason_code"] == "POLL_TIMEOUT"
    assert waits == [0, 0]
