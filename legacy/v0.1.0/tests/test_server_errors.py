# pyright: reportMissingImports=false
from typing import cast
from unittest.mock import AsyncMock

import pytest
from mcp import types

from modelscope_image_gen.server import handle_call_tool, service
from modelscope_image_gen.service import build_tool_success_result


def _as_call_tool_result(value: object) -> types.CallToolResult:
    return cast(types.CallToolResult, value)


@pytest.mark.asyncio
async def test_handle_call_tool_unknown_tool_returns_structured_error() -> None:
    result = _as_call_tool_result(await handle_call_tool("unknown_tool", {"prompt": "cat"}))

    assert result.isError is True
    assert result.structuredContent is not None
    err = result.structuredContent["error"]
    assert err["reason_code"] == "UNKNOWN_TOOL"
    assert err["category"] == "validation"
    assert err["retryable"] is False


@pytest.mark.asyncio
async def test_handle_call_tool_missing_prompt_returns_structured_error() -> None:
    result = _as_call_tool_result(await handle_call_tool("generate_image", {}))

    assert result.isError is True
    assert result.structuredContent is not None
    err = result.structuredContent["error"]
    assert err["reason_code"] == "MISSING_REQUIRED_ARGUMENT"
    assert err["category"] == "validation"
    assert err["retryable"] is False


@pytest.mark.asyncio
async def test_handle_call_tool_invalid_size_format_returns_validation_error() -> None:
    result = _as_call_tool_result(await handle_call_tool("generate_image", {"prompt": "cat", "size": "1024"}))

    assert result.isError is True
    assert result.structuredContent is not None
    err = result.structuredContent["error"]
    assert err["reason_code"] == "ARGUMENT_VALIDATION_FAILED"
    assert err["category"] == "validation"
    assert err["retryable"] is False


@pytest.mark.asyncio
async def test_handle_call_tool_out_of_range_size_returns_validation_error() -> None:
    result = _as_call_tool_result(await handle_call_tool("generate_image", {"prompt": "cat", "size": "32x32"}))

    assert result.isError is True
    assert result.structuredContent is not None
    err = result.structuredContent["error"]
    assert err["reason_code"] == "ARGUMENT_VALIDATION_FAILED"
    assert err["category"] == "validation"
    assert err["retryable"] is False


@pytest.mark.asyncio
async def test_handle_call_tool_missing_job_id_returns_validation_error() -> None:
    result = _as_call_tool_result(await handle_call_tool("get_image_generation_status", {}))

    assert result.isError is True
    assert result.structuredContent is not None
    err = result.structuredContent["error"]
    assert err["reason_code"] == "ARGUMENT_VALIDATION_FAILED"
    assert err["category"] == "validation"


@pytest.mark.asyncio
async def test_handle_call_tool_submit_dispatches_to_service(monkeypatch) -> None:
    monkeypatch.setattr(
        service,
        "submit_image_generation",
        AsyncMock(return_value=build_tool_success_result("ok", {"job_id": "job_1", "state": "submitted"})),
    )

    result = _as_call_tool_result(await handle_call_tool("submit_image_generation", {"prompt": "cat"}))

    assert result.isError is False
    assert result.structuredContent is not None
    assert result.structuredContent["data"]["job_id"] == "job_1"


@pytest.mark.asyncio
async def test_handle_call_tool_status_dispatches_to_service(monkeypatch) -> None:
    monkeypatch.setattr(
        service,
        "get_image_generation_status",
        AsyncMock(return_value=build_tool_success_result("ok", {"job_id": "job_2", "state": "in_progress"})),
    )

    result = _as_call_tool_result(await handle_call_tool("get_image_generation_status", {"job_id": "job_2"}))

    assert result.isError is False
    assert result.structuredContent is not None
    assert result.structuredContent["data"]["state"] == "in_progress"
