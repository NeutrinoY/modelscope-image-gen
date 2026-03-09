# pyright: reportMissingImports=false
import asyncio
from unittest.mock import AsyncMock

import pytest

from modelscope_image_gen.config import Settings
from modelscope_image_gen.service import ImageGenerationService


class DummyAsyncClient:
    def __init__(self, *args, **kwargs):
        return None

    async def __aenter__(self):
        return object()

    async def __aexit__(self, exc_type, exc, tb):
        return False


class FakeResponse:
    def __init__(self, *, status_code=200, headers=None, json_data=None, text=""):
        self.status_code = status_code
        self.headers = headers or {}
        self._json_data = json_data or {}
        self.text = text

    def json(self):
        return self._json_data


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

    text = result[0].text
    assert "配置错误" in text
    assert "stage: validation" in text
    assert "reason_code: MISSING_API_KEY" in text


@pytest.mark.asyncio
async def test_generate_image_reports_missing_task_id(monkeypatch, tmp_path) -> None:
    service = ImageGenerationService(Settings(modelscope_sdk_token="token"))

    monkeypatch.setattr("modelscope_image_gen.service.httpx.AsyncClient", DummyAsyncClient)

    async def fake_submit(client, **kwargs):
        return FakeResponse(
            status_code=200,
            headers={"X-Request-Id": "req-submit-1"},
            json_data={"ok": True},
        )

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

    text = result[0].text
    assert "任务提交失败" in text
    assert "stage: submit" in text
    assert "reason_code: TASK_ID_MISSING" in text
    assert "request_id: req-submit-1" in text


@pytest.mark.asyncio
async def test_generate_image_reports_task_failed(monkeypatch, tmp_path) -> None:
    service = ImageGenerationService(Settings(modelscope_sdk_token="token"))

    monkeypatch.setattr("modelscope_image_gen.service.httpx.AsyncClient", DummyAsyncClient)

    async def fake_sleep(_):
        return None

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)

    async def fake_submit(client, **kwargs):
        return FakeResponse(
            status_code=200,
            headers={"X-Request-Id": "req-submit-2"},
            json_data={"task_id": "task-1"},
        )

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

    text = result[0].text
    assert "图片生成失败" in text
    assert "stage: poll" in text
    assert "reason_code: TASK_FAILED" in text
    assert "detail: quota exceeded" in text


@pytest.mark.asyncio
async def test_generate_image_reports_unknown_task_status(monkeypatch, tmp_path) -> None:
    service = ImageGenerationService(Settings(modelscope_sdk_token="token"))

    monkeypatch.setattr("modelscope_image_gen.service.httpx.AsyncClient", DummyAsyncClient)

    async def fake_sleep(_):
        return None

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)

    async def fake_submit(client, **kwargs):
        return FakeResponse(
            status_code=200,
            headers={"X-Request-Id": "req-submit-3"},
            json_data={"task_id": "task-2"},
        )

    async def fake_poll(client, *, task_id):
        return FakeResponse(
            status_code=200,
            headers={"X-Request-Id": "req-poll-3"},
            json_data={"task_status": "CANCELLED"},
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

    text = result[0].text
    assert "任务状态异常" in text
    assert "stage: poll" in text
    assert "reason_code: UNKNOWN_TASK_STATUS" in text
    assert "CANCELLED" in text
