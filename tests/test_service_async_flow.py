# pyright: reportMissingImports=false
from __future__ import annotations

from io import BytesIO
from unittest.mock import AsyncMock

import pytest
from PIL import Image

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
    def __init__(self, *, status_code=200, headers=None, json_data=None, text="", content: bytes = b""):
        self.status_code = status_code
        self.headers = headers or {}
        self._json_data = json_data or {}
        self.text = text
        self.content = content

    def json(self):
        return self._json_data


def _png_bytes() -> bytes:
    image = Image.new("RGB", (2, 2), (255, 255, 255))
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.mark.asyncio
async def test_submit_status_result_flow(monkeypatch, tmp_path) -> None:
    service = ImageGenerationService(
        Settings(
            modelscope_sdk_token="token",
            modelscope_job_state_dir=str(tmp_path / "jobs"),
        )
    )

    monkeypatch.setattr("modelscope_image_gen.service.httpx.AsyncClient", DummyAsyncClient)

    async def fake_submit(client, **kwargs):
        return FakeResponse(
            status_code=200,
            headers={"X-Request-Id": "req-submit"},
            json_data={"task_id": "task-async-1"},
        )

    async def fake_poll(client, *, task_id):
        return FakeResponse(
            status_code=200,
            headers={"X-Request-Id": "req-poll"},
            json_data={"task_status": "SUCCEED", "output_images": ["https://example.com/a.png"]},
        )

    async def fake_download(client, *, image_url):
        return FakeResponse(
            status_code=200,
            headers={"X-Request-Id": "req-download", "Content-Type": "image/png"},
            json_data={},
            content=_png_bytes(),
        )

    monkeypatch.setattr(service.client, "submit_generation", AsyncMock(side_effect=fake_submit))
    monkeypatch.setattr(service.client, "poll_task", AsyncMock(side_effect=fake_poll))
    monkeypatch.setattr(service.client, "download_image", AsyncMock(side_effect=fake_download))

    submit_result = await service.submit_image_generation(
        prompt="cat",
        model="Qwen/Qwen-Image",
        size="1024x1024",
        output_filename="async.png",
        output_dir=str(tmp_path / "outputs"),
        poll_interval_seconds=1,
        max_poll_attempts=3,
        poll_backoff=False,
        max_poll_interval_seconds=5,
        negative_prompt=None,
        seed=None,
    )

    assert submit_result.isError is False
    submit_data = submit_result.structuredContent["data"]
    job_id = submit_data["job_id"]
    assert submit_data["task_id"] == "task-async-1"

    status_result = await service.get_image_generation_status(job_id=job_id)
    assert status_result.isError is False
    status_data = status_result.structuredContent["data"]
    assert status_data["state"] == "succeeded"
    assert status_data["result_ready"] is True
    assert status_data["remote_image_url"] == "https://example.com/a.png"

    result_result = await service.get_image_generation_result(job_id=job_id)
    assert result_result.isError is False
    result_data = result_result.structuredContent["data"]
    assert result_data["state"] == "succeeded"
    assert result_data["output_filename"] == "async.png"


@pytest.mark.asyncio
async def test_get_result_before_ready_returns_result_not_ready(monkeypatch, tmp_path) -> None:
    service = ImageGenerationService(
        Settings(
            modelscope_sdk_token="token",
            modelscope_job_state_dir=str(tmp_path / "jobs"),
        )
    )

    monkeypatch.setattr("modelscope_image_gen.service.httpx.AsyncClient", DummyAsyncClient)

    async def fake_submit(client, **kwargs):
        return FakeResponse(
            status_code=200,
            headers={"X-Request-Id": "req-submit"},
            json_data={"task_id": "task-async-2"},
        )

    monkeypatch.setattr(service.client, "submit_generation", AsyncMock(side_effect=fake_submit))

    submit_result = await service.submit_image_generation(
        prompt="cat",
        model="Qwen/Qwen-Image",
        size="1024x1024",
        output_filename="async.png",
        output_dir=str(tmp_path / "outputs"),
        poll_interval_seconds=1,
        max_poll_attempts=3,
        poll_backoff=False,
        max_poll_interval_seconds=5,
        negative_prompt=None,
        seed=None,
    )

    job_id = submit_result.structuredContent["data"]["job_id"]
    result_result = await service.get_image_generation_result(job_id=job_id)

    assert result_result.isError is True
    err = result_result.structuredContent["error"]
    assert err["reason_code"] == "RESULT_NOT_READY"
