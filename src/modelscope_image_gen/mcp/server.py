from __future__ import annotations

# pyright: reportMissingImports=false, reportAttributeAccessIssue=false, reportCallIssue=false
import asyncio
import logging
from typing import Any

from mcp import types
from mcp.server import NotificationOptions, Server
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server

from ..config import get_settings
from ..services import ImageGenerationService, build_tool_error_result
from .argument_validation import validate_generation_args, validate_job_id_args
from .tool_metadata import SUPPORTED_TOOL_NAMES, build_tool_list

settings = get_settings()
logging.basicConfig(level=getattr(logging, settings.modelscope_log_level.upper(), logging.INFO))
logger = logging.getLogger("modelscope-image-gen")

app = Server("modelscope-image-gen")
service = ImageGenerationService(settings)


@app.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    return build_tool_list(settings.default_model)


@app.call_tool()
async def handle_call_tool(name: str, arguments: dict[str, Any] | None) -> types.CallToolResult:
    if name not in SUPPORTED_TOOL_NAMES:
        return build_tool_error_result(
            "工具调用失败",
            stage="validation",
            reason_code="UNKNOWN_TOOL",
            category="validation",
            retryable=False,
            detail=f"不支持的工具名 {name}",
            suggestion="使用 list_tools 获取可用工具，并调用对应工具",
        )

    args = arguments or {}
    if name in {"get_image_generation_status", "get_image_generation_result"}:
        job_id, validation_error = validate_job_id_args(args)
        if validation_error is not None:
            return validation_error

        if name == "get_image_generation_status":
            return await service.get_image_generation_status(job_id=job_id or "")
        return await service.get_image_generation_result(job_id=job_id or "")

    validated_args, validation_error = validate_generation_args(args, default_model=settings.default_model)
    if validation_error is not None:
        return validation_error
    if validated_args is None:
        return build_tool_error_result(
            "参数校验失败",
            stage="validation",
            reason_code="ARGUMENT_VALIDATION_FAILED",
            category="validation",
            retryable=False,
            detail="参数解析失败",
            suggestion="检查参数类型与取值范围后重试",
        )

    prompt = validated_args.prompt
    model = validated_args.model
    size = validated_args.size
    output_filename = validated_args.output_filename
    output_dir = validated_args.output_dir

    if name == "submit_image_generation":
        return await service.submit_image_generation(
            prompt=prompt,
            model=model,
            size=size,
            output_filename=output_filename,
            output_dir=output_dir,
            poll_interval_seconds=validated_args.poll_interval_seconds,
            max_poll_attempts=validated_args.max_poll_attempts,
            poll_backoff=validated_args.poll_backoff,
            max_poll_interval_seconds=validated_args.max_poll_interval_seconds,
            negative_prompt=validated_args.negative_prompt,
            seed=validated_args.seed,
        )

    return await service.generate_image(
        prompt=prompt,
        model=model,
        size=size,
        output_filename=output_filename,
        output_dir=output_dir,
        poll_interval_seconds=validated_args.poll_interval_seconds,
        max_poll_attempts=validated_args.max_poll_attempts,
        poll_backoff=validated_args.poll_backoff,
        max_poll_interval_seconds=validated_args.max_poll_interval_seconds,
        negative_prompt=validated_args.negative_prompt,
        seed=validated_args.seed,
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
