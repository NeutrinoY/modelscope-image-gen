# pyright: reportMissingImports=false
import asyncio
from unittest.mock import AsyncMock

import httpx
import pytest
from PIL import Image
from service_test_helpers import DummyAsyncClient, FakeResponse, png_bytes_rgba

from modelscope_image_gen.config import Settings
from modelscope_image_gen.service import ImageGenerationService


@pytest.mark.asyncio
async def test_generate_image_success_path_saves_jpeg_with_rgb_conversion(monkeypatch, tmp_path) -> None:
    service = ImageGenerationService(Settings(modelscope_sdk_token="token"))

    monkeypatch.setattr("modelscope_image_gen.services.workflows.generate.httpx.AsyncClient", DummyAsyncClient)

    async def fake_sleep(_):
        return None

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)

    async def fake_submit(client, **kwargs):
        return FakeResponse(status_code=200, headers={"X-Request-Id": "req-submit-ok"}, json_data={"task_id": "task-success"})

    async def fake_poll(client, *, task_id):
        return FakeResponse(
            status_code=200,
            headers={"X-Request-Id": "req-poll-ok"},
            json_data={"task_status": "SUCCEED", "output_images": ["https://example.com/image.png"]},
        )

    async def fake_download(client, *, image_url):
        return FakeResponse(
            status_code=200,
            headers={"X-Request-Id": "req-download-ok", "Content-Type": "image/png"},
            text="",
            json_data={},
            content=png_bytes_rgba(),
        )

    monkeypatch.setattr(service.client, "submit_generation", AsyncMock(side_effect=fake_submit))
    monkeypatch.setattr(service.client, "poll_task", AsyncMock(side_effect=fake_poll))
    monkeypatch.setattr(service.client, "download_image", AsyncMock(side_effect=fake_download))

    output_file = tmp_path / "generated.jpg"

    result = await service.generate_image(
        prompt="cat",
        model="Qwen/Qwen-Image",
        size="1024x1024",
        output_filename=output_file.name,
        output_dir=str(tmp_path),
        poll_interval_seconds=0,
        max_poll_attempts=1,
        poll_backoff=False,
        max_poll_interval_seconds=1,
        negative_prompt=None,
        seed=None,
    )

    assert result.isError is False
    assert result.structuredContent is not None
    assert result.structuredContent["ok"] is True
    assert output_file.exists()
    saved = Image.open(output_file)
    assert saved.mode == "RGB"


@pytest.mark.asyncio
async def test_generate_image_accepts_octet_stream_with_valid_image(monkeypatch, tmp_path) -> None:
    service = ImageGenerationService(Settings(modelscope_sdk_token="token"))

    monkeypatch.setattr("modelscope_image_gen.services.workflows.generate.httpx.AsyncClient", DummyAsyncClient)

    async def fake_sleep(_):
        return None

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)

    async def fake_submit(client, **kwargs):
        return FakeResponse(status_code=200, headers={"X-Request-Id": "req-submit-ok"}, json_data={"task_id": "task-success"})

    async def fake_poll(client, *, task_id):
        return FakeResponse(
            status_code=200,
            headers={"X-Request-Id": "req-poll-ok"},
            json_data={"task_status": "SUCCEED", "output_images": ["https://example.com/image.bin"]},
        )

    async def fake_download(client, *, image_url):
        return FakeResponse(
            status_code=200,
            headers={"X-Request-Id": "req-download-ok", "Content-Type": "application/octet-stream"},
            text="",
            json_data={},
            content=png_bytes_rgba(),
        )

    monkeypatch.setattr(service.client, "submit_generation", AsyncMock(side_effect=fake_submit))
    monkeypatch.setattr(service.client, "poll_task", AsyncMock(side_effect=fake_poll))
    monkeypatch.setattr(service.client, "download_image", AsyncMock(side_effect=fake_download))

    output_file = tmp_path / "generated_octet.jpg"

    result = await service.generate_image(
        prompt="cat",
        model="Qwen/Qwen-Image",
        size="1024x1024",
        output_filename=output_file.name,
        output_dir=str(tmp_path),
        poll_interval_seconds=0,
        max_poll_attempts=1,
        poll_backoff=False,
        max_poll_interval_seconds=1,
        negative_prompt=None,
        seed=None,
    )

    assert result.isError is False
    assert output_file.exists()


@pytest.mark.asyncio
async def test_generate_image_uses_retry_after_when_http_status_error(monkeypatch, tmp_path) -> None:
    service = ImageGenerationService(Settings(modelscope_sdk_token="token"))

    monkeypatch.setattr("modelscope_image_gen.services.workflows.generate.httpx.AsyncClient", DummyAsyncClient)

    request = httpx.Request("POST", "https://api-inference.modelscope.cn/v1/images/generations")
    response = httpx.Response(429, request=request, headers={"Retry-After": "7", "X-Request-Id": "req-http-429"}, text='{"error": "rate limit"}')
    http_error = httpx.HTTPStatusError("too many requests", request=request, response=response)

    monkeypatch.setattr(service.client, "submit_generation", AsyncMock(side_effect=http_error))

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
    assert err["stage"] == "submit"
    assert err["reason_code"] == "SUBMIT_HTTP_ERROR"
    assert err["retry_after_seconds"] == 7
    assert err["request_id"] == "req-http-429"
