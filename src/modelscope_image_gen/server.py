from __future__ import annotations

# pyright: reportMissingImports=false
import asyncio
import logging
from typing import Any

from mcp import types
from mcp.server import NotificationOptions, Server
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server

from .config import get_settings
from .service import ImageGenerationService

settings = get_settings()
logging.basicConfig(level=getattr(logging, settings.modelscope_log_level.upper(), logging.INFO))
logger = logging.getLogger("modelscope-image-gen")

app = Server("modelscope-image-gen")
service = ImageGenerationService(settings)


@app.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="generate_image",
            description="使用ModelScope生成图片",
            inputSchema={
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": "图片生成提示词",
                    },
                    "model": {
                        "type": "string",
                        "description": f"模型名称，默认为 {settings.default_model}",
                        "default": settings.default_model,
                    },
                    "size": {
                        "type": "string",
                        "description": (
                            "生成图像分辨率大小，Qwen-Image支持:[64x64,1664x1664]，"
                            "默认为 '1024x1024'"
                        ),
                        "default": "1024x1024",
                    },
                    "output_filename": {
                        "type": "string",
                        "description": "输出图片文件名，默认为 'result_image.jpg'",
                        "default": "result_image.jpg",
                    },
                    "output_dir": {
                        "type": "string",
                        "description": "输出目录路径，默认为 './outputs'",
                        "default": "./outputs",
                    },
                    "poll_interval_seconds": {
                        "type": "number",
                        "description": "轮询基础间隔(秒)，默认取环境变量或 5",
                    },
                    "max_poll_attempts": {
                        "type": "integer",
                        "description": "最大轮询次数，默认取环境变量或 120（约 10 分钟）",
                    },
                    "poll_backoff": {
                        "type": "boolean",
                        "description": "是否开启指数退避，默认取环境变量或 false",
                    },
                    "max_poll_interval_seconds": {
                        "type": "number",
                        "description": "指数退避的最大间隔(秒)，默认取环境变量或 30",
                    },
                    "negative_prompt": {
                        "type": "string",
                        "description": "负向提示词，可选",
                    },
                    "seed": {
                        "type": "integer",
                        "description": "随机种子，可选",
                    },
                },
                "required": ["prompt"],
            },
        )
    ]


@app.call_tool()
async def handle_call_tool(name: str, arguments: dict[str, Any]) -> list[types.TextContent]:
    if name != "generate_image":
        raise ValueError(f"未知工具: {name}")

    return await service.generate_image(
        prompt=arguments["prompt"],
        model=arguments.get("model", settings.default_model),
        size=arguments.get("size", "1024x1024"),
        output_filename=arguments.get("output_filename", "result_image.jpg"),
        output_dir=arguments.get("output_dir", "./outputs"),
        poll_interval_seconds=arguments.get("poll_interval_seconds"),
        max_poll_attempts=arguments.get("max_poll_attempts"),
        poll_backoff=arguments.get("poll_backoff"),
        max_poll_interval_seconds=arguments.get("max_poll_interval_seconds"),
        negative_prompt=arguments.get("negative_prompt"),
        seed=arguments.get("seed"),
    )


async def main() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="modelscope-image-gen",
                server_version="0.1.0",
                capabilities=app.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


def cli_main() -> None:
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("服务器已停止")


if __name__ == "__main__":
    cli_main()
