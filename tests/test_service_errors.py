# pyright: reportMissingImports=false
import asyncio
from io import BytesIO
from unittest.mock import AsyncMock

import httpx
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


def _png_bytes_rgba() -> bytes:
    image = Image.new("RGBA", (2, 2), (255, 0, 0, 128))
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


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

    assert result.isError is True
    err = result.structuredContent["error"]
    assert err["reason_code"] == "TASK_ID_MISSING"
    assert err["category"] == "upstream_response"
    assert err["retryable"] is True


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

    assert result.isError is True
    err = result.structuredContent["error"]
    assert err["reason_code"] == "TASK_FAILED"
    assert err["category"] == "upstream_task"
    assert err["retryable"] is True
    assert err["retry_after_seconds"] == 1


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

    assert result.isError is True
    err = result.structuredContent["error"]
    assert err["reason_code"] == "UNKNOWN_TASK_STATUS"
    assert err["category"] == "upstream_response"
    assert err["retryable"] is False


@pytest.mark.asyncio
async def test_generate_image_redacts_sensitive_fields_in_body(monkeypatch) -> None:
    service = ImageGenerationService(Settings(modelscope_sdk_token="token"))

    monkeypatch.setattr("modelscope_image_gen.service.httpx.AsyncClient", DummyAsyncClient)

    async def fake_submit(client, **kwargs):
        return FakeResponse(
            status_code=200,
            headers={"X-Request-Id": "req-submit-4"},
            json_data={
                "error": "bad",
                "token": "abc123",
                "nested": {"authorization": "Bearer SECRET_TOKEN"},
            },
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

    err = result.structuredContent["error"]
    assert err["body"]["token"] == "[REDACTED]"
    assert err["body"]["nested"]["authorization"] == "[REDACTED]"


@pytest.mark.asyncio
async def test_generate_image_success_path_saves_jpeg_with_rgb_conversion(monkeypatch, tmp_path) -> None:
    service = ImageGenerationService(Settings(modelscope_sdk_token="token"))

    monkeypatch.setattr("modelscope_image_gen.service.httpx.AsyncClient", DummyAsyncClient)

    async def fake_sleep(_):
        return None

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)

    async def fake_submit(client, **kwargs):
        return FakeResponse(
            status_code=200,
            headers={"X-Request-Id": "req-submit-ok"},
            json_data={"task_id": "task-success"},
        )

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
            content=_png_bytes_rgba(),
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
    assert result.structuredContent["ok"] is True
    assert output_file.exists()
    saved = Image.open(output_file)
    assert saved.mode == "RGB"


@pytest.mark.asyncio
async def test_generate_image_uses_retry_after_when_http_status_error(monkeypatch, tmp_path) -> None:
    service = ImageGenerationService(Settings(modelscope_sdk_token="token"))

    monkeypatch.setattr("modelscope_image_gen.service.httpx.AsyncClient", DummyAsyncClient)

    request = httpx.Request("POST", "https://api-inference.modelscope.cn/v1/images/generations")
    response = httpx.Response(
        429,
        request=request,
        headers={"Retry-After": "7", "X-Request-Id": "req-http-429"},
        text='{"error": "rate limit"}',
    )
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
    err = result.structuredContent["error"]
    assert err["stage"] == "submit"
    assert err["reason_code"] == "SUBMIT_HTTP_ERROR"
    assert err["retry_after_seconds"] == 7
    assert err["request_id"] == "req-http-429"


@pytest.mark.asyncio
async def test_generate_image_timeout_uses_backoff_schedule(monkeypatch, tmp_path) -> None:
    service = ImageGenerationService(Settings(modelscope_sdk_token="token"))

    monkeypatch.setattr("modelscope_image_gen.service.httpx.AsyncClient", DummyAsyncClient)

    waits: list[float] = []

    async def fake_sleep(seconds):
        waits.append(seconds)
        return None

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)

    async def fake_submit(client, **kwargs):
        return FakeResponse(
            status_code=200,
            headers={"X-Request-Id": "req-submit-timeout"},
            json_data={"task_id": "task-timeout"},
        )

    async def fake_poll(client, *, task_id):
        return FakeResponse(
            status_code=200,
            headers={"X-Request-Id": "req-poll-timeout"},
            json_data={"task_status": "RUNNING"},
        )

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
    err = result.structuredContent["error"]
    assert err["reason_code"] == "POLL_TIMEOUT"
    assert waits == [1, 2, 3]


@pytest.mark.asyncio
async def test_generate_image_treats_processing_as_in_progress(monkeypatch, tmp_path) -> None:
    service = ImageGenerationService(Settings(modelscope_sdk_token="token"))

    monkeypatch.setattr("modelscope_image_gen.service.httpx.AsyncClient", DummyAsyncClient)

    waits: list[float] = []

    async def fake_sleep(seconds):
        waits.append(seconds)
        return None

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)

    async def fake_submit(client, **kwargs):
        return FakeResponse(
            status_code=200,
            headers={"X-Request-Id": "req-submit-processing"},
            json_data={"task_id": "task-processing"},
        )

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
    err = result.structuredContent["error"]
    assert err["reason_code"] == "POLL_TIMEOUT"
    assert waits == [0, 0]
