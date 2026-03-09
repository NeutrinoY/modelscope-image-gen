from __future__ import annotations

# pyright: reportMissingImports=false
import asyncio
import logging
import re
from typing import Any

from mcp import types
from mcp.server import NotificationOptions, Server
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server
from pydantic import BaseModel, Field, ValidationError

from .config import get_settings
from .service import ImageGenerationService, build_tool_error_result

settings = get_settings()
logging.basicConfig(level=getattr(logging, settings.modelscope_log_level.upper(), logging.INFO))
logger = logging.getLogger("modelscope-image-gen")

app = Server("modelscope-image-gen")
service = ImageGenerationService(settings)

_SIZE_PATTERN = re.compile(r"^(\d+)x(\d+)$")


class GenerateImageArgs(BaseModel):
    prompt: str = Field(min_length=1)
    model: str = Field(default=settings.default_model, min_length=1)
    size: str = Field(default="1024x1024")
    output_filename: str = Field(default="result_image.jpg", min_length=1)
    output_dir: str = Field(default="./outputs", min_length=1)
    poll_interval_seconds: float | None = Field(default=None, ge=0)
    max_poll_attempts: int | None = Field(default=None, ge=1)
    poll_backoff: bool | None = None
    max_poll_interval_seconds: float | None = Field(default=None, ge=0)
    negative_prompt: str | None = None
    seed: int | None = None


class JobIdArgs(BaseModel):
    job_id: str = Field(min_length=1)


def _normalize_size(value: str) -> str:
    match = _SIZE_PATTERN.fullmatch(value.strip())
    if match is None:
        raise ValueError("size must follow WIDTHxHEIGHT, e.g. 1024x1024")
    width = int(match.group(1))
    height = int(match.group(2))
    if width < 64 or width > 1664 or height < 64 or height > 1664:
        raise ValueError("size width/height must be between 64 and 1664")
    return f"{width}x{height}"


def _validation_error_detail(exc: ValidationError) -> str:
    lines: list[str] = []
    for item in exc.errors():
        loc_raw = item.get("loc", ())
        loc = ".".join(str(part) for part in loc_raw) if loc_raw else "arguments"
        msg = str(item.get("msg", "invalid value"))
        lines.append(f"{loc}: {msg}")
    return "; ".join(lines)


@app.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="submit_image_generation",
            description="提交图片生成任务并返回可查询的 job_id",
            inputSchema={
                "type": "object",
                "properties": {
                    "prompt": {"type": "string", "description": "图片生成提示词"},
                    "model": {
                        "type": "string",
                        "description": f"模型名称，默认为 {settings.default_model}",
                        "default": settings.default_model,
                    },
                    "size": {
                        "type": "string",
                        "description": "生成图像分辨率大小，格式 WIDTHxHEIGHT",
                        "default": "1024x1024",
                    },
                    "output_filename": {
                        "type": "string",
                        "description": "输出图片文件名",
                        "default": "result_image.jpg",
                    },
                    "output_dir": {
                        "type": "string",
                        "description": "输出目录路径",
                        "default": "./outputs",
                    },
                    "poll_interval_seconds": {"type": "number", "description": "轮询基础间隔(秒)"},
                    "max_poll_attempts": {"type": "integer", "description": "最大轮询次数"},
                    "poll_backoff": {"type": "boolean", "description": "是否开启指数退避"},
                    "max_poll_interval_seconds": {"type": "number", "description": "指数退避最大间隔(秒)"},
                    "negative_prompt": {"type": "string", "description": "负向提示词，可选"},
                    "seed": {"type": "integer", "description": "随机种子，可选"},
                },
                "required": ["prompt"],
            },
        ),
        types.Tool(
            name="get_image_generation_status",
            description="根据 job_id 查询任务状态",
            inputSchema={
                "type": "object",
                "properties": {
                    "job_id": {"type": "string", "description": "提交时返回的任务标识"},
                },
                "required": ["job_id"],
            },
        ),
        types.Tool(
            name="get_image_generation_result",
            description="根据 job_id 获取并保存生成结果",
            inputSchema={
                "type": "object",
                "properties": {
                    "job_id": {"type": "string", "description": "提交时返回的任务标识"},
                },
                "required": ["job_id"],
            },
        ),
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
                        "description": ("生成图像分辨率大小，Qwen-Image支持:[64x64,1664x1664]，默认为 '1024x1024'"),
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
        ),
    ]


@app.call_tool()
async def handle_call_tool(name: str, arguments: dict[str, Any] | None) -> types.CallToolResult:
    if name not in {
        "generate_image",
        "submit_image_generation",
        "get_image_generation_status",
        "get_image_generation_result",
    }:
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
        try:
            parsed_job_args = JobIdArgs.model_validate(args)
        except ValidationError as exc:
            return build_tool_error_result(
                "参数校验失败",
                stage="validation",
                reason_code="ARGUMENT_VALIDATION_FAILED",
                category="validation",
                retryable=False,
                detail=_validation_error_detail(exc),
                suggestion="传入非空字符串 job_id 后重试",
            )

        job_id = parsed_job_args.job_id.strip()
        if not job_id:
            return build_tool_error_result(
                "参数校验失败",
                stage="validation",
                reason_code="MISSING_REQUIRED_ARGUMENT",
                category="validation",
                retryable=False,
                detail="缺少必填参数 job_id",
                suggestion="传入非空字符串 job_id 后重试",
            )

        if name == "get_image_generation_status":
            return await service.get_image_generation_status(job_id=job_id)
        return await service.get_image_generation_result(job_id=job_id)

    try:
        parsed_args = GenerateImageArgs.model_validate(args)
    except ValidationError as exc:
        has_missing_prompt = any(item.get("type") == "missing" and item.get("loc") == ("prompt",) for item in exc.errors())
        if has_missing_prompt:
            return build_tool_error_result(
                "参数校验失败",
                stage="validation",
                reason_code="MISSING_REQUIRED_ARGUMENT",
                category="validation",
                retryable=False,
                detail="缺少必填参数 prompt",
                suggestion="传入非空字符串 prompt 后重试",
            )

        return build_tool_error_result(
            "参数校验失败",
            stage="validation",
            reason_code="ARGUMENT_VALIDATION_FAILED",
            category="validation",
            retryable=False,
            detail=_validation_error_detail(exc),
            suggestion="检查参数类型与取值范围后重试",
        )

    try:
        prompt = parsed_args.prompt.strip()
        model = parsed_args.model.strip()
        output_filename = parsed_args.output_filename.strip()
        output_dir = parsed_args.output_dir.strip()
        size = _normalize_size(parsed_args.size)
    except ValueError as exc:
        return build_tool_error_result(
            "参数校验失败",
            stage="validation",
            reason_code="ARGUMENT_VALIDATION_FAILED",
            category="validation",
            retryable=False,
            detail=str(exc),
            suggestion="检查参数类型与取值范围后重试",
        )

    if not prompt:
        return build_tool_error_result(
            "参数校验失败",
            stage="validation",
            reason_code="MISSING_REQUIRED_ARGUMENT",
            category="validation",
            retryable=False,
            detail="缺少必填参数 prompt",
            suggestion="传入非空字符串 prompt 后重试",
        )

    if not model or not output_filename or not output_dir:
        return build_tool_error_result(
            "参数校验失败",
            stage="validation",
            reason_code="ARGUMENT_VALIDATION_FAILED",
            category="validation",
            retryable=False,
            detail="model/output_filename/output_dir 必须为非空字符串",
            suggestion="检查参数类型与取值范围后重试",
        )

    if name == "submit_image_generation":
        return await service.submit_image_generation(
            prompt=prompt,
            model=model,
            size=size,
            output_filename=output_filename,
            output_dir=output_dir,
            poll_interval_seconds=parsed_args.poll_interval_seconds,
            max_poll_attempts=parsed_args.max_poll_attempts,
            poll_backoff=parsed_args.poll_backoff,
            max_poll_interval_seconds=parsed_args.max_poll_interval_seconds,
            negative_prompt=parsed_args.negative_prompt,
            seed=parsed_args.seed,
        )

    return await service.generate_image(
        prompt=prompt,
        model=model,
        size=size,
        output_filename=output_filename,
        output_dir=output_dir,
        poll_interval_seconds=parsed_args.poll_interval_seconds,
        max_poll_attempts=parsed_args.max_poll_attempts,
        poll_backoff=parsed_args.poll_backoff,
        max_poll_interval_seconds=parsed_args.max_poll_interval_seconds,
        negative_prompt=parsed_args.negative_prompt,
        seed=parsed_args.seed,
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
