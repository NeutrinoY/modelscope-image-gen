# pyright: reportMissingImports=false
import json
from unittest.mock import AsyncMock, Mock

import pytest

from modelscope_image_gen.client import ModelScopeClient


@pytest.mark.asyncio
async def test_submit_generation_includes_optional_fields() -> None:
    api_client = ModelScopeClient(api_base="https://api-inference.modelscope.cn/", api_key="token")

    http_client = AsyncMock()
    response = Mock()
    response.raise_for_status = Mock()
    http_client.post = AsyncMock(return_value=response)

    await api_client.submit_generation(
        http_client,
        model="Qwen/Qwen-Image",
        prompt="A golden cat",
        size="1024x1024",
        negative_prompt="blurry",
        seed=123,
    )

    kwargs = http_client.post.await_args.kwargs
    payload = json.loads(kwargs["content"].decode("utf-8"))

    assert kwargs["headers"]["X-ModelScope-Async-Mode"] == "true"
    assert payload["model"] == "Qwen/Qwen-Image"
    assert payload["prompt"] == "A golden cat"
    assert payload["size"] == "1024x1024"
    assert payload["negative_prompt"] == "blurry"
    assert payload["seed"] == 123


@pytest.mark.asyncio
async def test_submit_generation_omits_optional_fields_when_none() -> None:
    api_client = ModelScopeClient(api_base="https://api-inference.modelscope.cn/", api_key="token")

    http_client = AsyncMock()
    response = Mock()
    response.raise_for_status = Mock()
    http_client.post = AsyncMock(return_value=response)

    await api_client.submit_generation(
        http_client,
        model="Qwen/Qwen-Image",
        prompt="A golden cat",
        size="1024x1024",
        negative_prompt=None,
        seed=None,
    )

    kwargs = http_client.post.await_args.kwargs
    payload = json.loads(kwargs["content"].decode("utf-8"))

    assert "negative_prompt" not in payload
    assert "seed" not in payload


@pytest.mark.asyncio
async def test_client_uses_per_phase_timeouts() -> None:
    api_client = ModelScopeClient(
        api_base="https://api-inference.modelscope.cn/",
        api_key="token",
    )

    http_client = AsyncMock()

    submit_response = Mock()
    submit_response.raise_for_status = Mock()
    http_client.post = AsyncMock(return_value=submit_response)

    poll_response = Mock()
    poll_response.raise_for_status = Mock()
    http_client.get = AsyncMock(return_value=poll_response)

    await api_client.submit_generation(
        http_client,
        model="Qwen/Qwen-Image",
        prompt="A golden cat",
        size="1024x1024",
        negative_prompt=None,
        seed=None,
    )
    await api_client.poll_task(http_client, task_id="task-1")
    await api_client.download_image(http_client, image_url="https://example.com/i.png")

    submit_timeout = http_client.post.await_args.kwargs.get("timeout")
    first_get_timeout = http_client.get.await_args_list[0].kwargs.get("timeout")
    second_get_timeout = http_client.get.await_args_list[1].kwargs.get("timeout")

    assert submit_timeout == 30.0
    assert first_get_timeout == 30.0
    assert second_get_timeout == 60.0
