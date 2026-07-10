import mcp
import pytest

from modelscope_image_gen.bootstrap import build_runtime
from modelscope_image_gen.infrastructure.config.settings import Settings


@pytest.mark.anyio
async def test_official_in_memory_client_lists_and_calls_tools(tmp_path) -> None:
    async with build_runtime(Settings(data_dir=tmp_path)) as runtime:
        async with mcp.Client(runtime.server) as client:
            listing = await client.list_tools()
            result = await client.call_tool("list_image_generations", {})

    assert [tool.name for tool in listing.tools] == [
        "submit_image_generation",
        "check_image_generation",
        "fetch_image_generation_result",
        "list_image_generations",
        "generate_image",
    ]
    assert result.is_error is False
    assert result.structured_content["data"]["items"] == []
