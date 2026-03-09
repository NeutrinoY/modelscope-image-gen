# pyright: reportMissingImports=false
import pytest

from modelscope_image_gen.server import handle_call_tool


@pytest.mark.asyncio
async def test_handle_call_tool_unknown_tool_returns_structured_error() -> None:
    result = await handle_call_tool("unknown_tool", {"prompt": "cat"})

    assert result.isError is True
    assert result.structuredContent is not None
    err = result.structuredContent["error"]
    assert err["reason_code"] == "UNKNOWN_TOOL"
    assert err["category"] == "validation"
    assert err["retryable"] is False


@pytest.mark.asyncio
async def test_handle_call_tool_missing_prompt_returns_structured_error() -> None:
    result = await handle_call_tool("generate_image", {})

    assert result.isError is True
    assert result.structuredContent is not None
    err = result.structuredContent["error"]
    assert err["reason_code"] == "MISSING_REQUIRED_ARGUMENT"
    assert err["category"] == "validation"
    assert err["retryable"] is False


@pytest.mark.asyncio
async def test_handle_call_tool_invalid_size_format_returns_validation_error() -> None:
    result = await handle_call_tool("generate_image", {"prompt": "cat", "size": "1024"})

    assert result.isError is True
    assert result.structuredContent is not None
    err = result.structuredContent["error"]
    assert err["reason_code"] == "ARGUMENT_VALIDATION_FAILED"
    assert err["category"] == "validation"
    assert err["retryable"] is False


@pytest.mark.asyncio
async def test_handle_call_tool_out_of_range_size_returns_validation_error() -> None:
    result = await handle_call_tool("generate_image", {"prompt": "cat", "size": "32x32"})

    assert result.isError is True
    assert result.structuredContent is not None
    err = result.structuredContent["error"]
    assert err["reason_code"] == "ARGUMENT_VALIDATION_FAILED"
    assert err["category"] == "validation"
    assert err["retryable"] is False
