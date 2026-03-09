# pyright: reportMissingImports=false
import pytest

from modelscope_image_gen.server import handle_call_tool


@pytest.mark.asyncio
async def test_handle_call_tool_unknown_tool_returns_structured_error() -> None:
    result = await handle_call_tool("unknown_tool", {"prompt": "cat"})
    text = result[0].text

    assert "工具调用失败" in text
    assert "stage: validation" in text
    assert "reason_code: UNKNOWN_TOOL" in text


@pytest.mark.asyncio
async def test_handle_call_tool_missing_prompt_returns_structured_error() -> None:
    result = await handle_call_tool("generate_image", {})
    text = result[0].text

    assert "参数校验失败" in text
    assert "stage: validation" in text
    assert "reason_code: MISSING_REQUIRED_ARGUMENT" in text
