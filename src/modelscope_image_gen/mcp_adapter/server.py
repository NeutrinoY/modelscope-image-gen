from __future__ import annotations

import mcp
import mcp_types
from mcp.server.lowlevel import Server

from modelscope_image_gen import __version__
from modelscope_image_gen.mcp_adapter.registry import ToolRegistry


def create_server(registry: ToolRegistry) -> Server:
    async def list_tools(_context, _params) -> mcp_types.ListToolsResult:
        return mcp_types.ListToolsResult(tools=registry.tools())

    async def call_tool(_context, params: mcp_types.CallToolRequestParams) -> mcp_types.CallToolResult:
        try:
            return await registry.call(params.name, params.arguments)
        except KeyError as exc:
            raise mcp.MCPError(-32601, f"Unknown tool: {params.name}") from exc

    return Server(
        "modelscope-image-gen-mcp",
        version=__version__,
        title="ModelScope Image Gen MCP",
        description="Local-first reliable ModelScope text-to-image generation.",
        instructions=(
            "Use submit_image_generation, then check_image_generation, then fetch_image_generation_result. "
            "Use list_image_generations to recover job IDs."
        ),
        on_list_tools=list_tools,
        on_call_tool=call_tool,
    )
