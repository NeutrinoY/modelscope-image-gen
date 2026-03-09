from __future__ import annotations

# pyright: reportMissingImports=false, reportAttributeAccessIssue=false
import re
from dataclasses import dataclass
from typing import Any

from mcp import types
from pydantic import BaseModel, Field, ValidationError

from ..services import build_tool_error_result

_SIZE_PATTERN = re.compile(r"^(\d+)x(\d+)$")


class GenerateImageArgs(BaseModel):
    prompt: str = Field(min_length=1)
    model: str = Field(min_length=1)
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


@dataclass(frozen=True)
class NormalizedGenerationArgs:
    prompt: str
    model: str
    size: str
    output_filename: str
    output_dir: str
    poll_interval_seconds: float | None
    max_poll_attempts: int | None
    poll_backoff: bool | None
    max_poll_interval_seconds: float | None
    negative_prompt: str | None
    seed: int | None


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


def validate_job_id_args(args: dict[str, Any]) -> tuple[str | None, types.CallToolResult | None]:
    try:
        parsed_job_args = JobIdArgs.model_validate(args)
    except ValidationError as exc:
        return None, build_tool_error_result(
            "Argument validation failed",
            stage="validation",
            reason_code="ARGUMENT_VALIDATION_FAILED",
            category="validation",
            retryable=False,
            detail=_validation_error_detail(exc),
            suggestion="Provide a non-empty job_id and try again",
        )

    job_id = parsed_job_args.job_id.strip()
    if not job_id:
        return None, build_tool_error_result(
            "Argument validation failed",
            stage="validation",
            reason_code="MISSING_REQUIRED_ARGUMENT",
            category="validation",
            retryable=False,
            detail="Missing required argument: job_id",
            suggestion="Provide a non-empty job_id and try again",
        )
    return job_id, None


def validate_generation_args(args: dict[str, Any], *, default_model: str) -> tuple[NormalizedGenerationArgs | None, types.CallToolResult | None]:
    try:
        parsed_args = GenerateImageArgs.model_validate({**args, "model": args.get("model", default_model)})
    except ValidationError as exc:
        has_missing_prompt = any(item.get("type") == "missing" and item.get("loc") == ("prompt",) for item in exc.errors())
        if has_missing_prompt:
            return None, build_tool_error_result(
                "Argument validation failed",
                stage="validation",
                reason_code="MISSING_REQUIRED_ARGUMENT",
                category="validation",
                retryable=False,
                detail="Missing required argument: prompt",
                suggestion="Provide a non-empty prompt and try again",
            )

        return None, build_tool_error_result(
            "Argument validation failed",
            stage="validation",
            reason_code="ARGUMENT_VALIDATION_FAILED",
            category="validation",
            retryable=False,
            detail=_validation_error_detail(exc),
            suggestion="Check argument types and value ranges, then try again",
        )

    try:
        prompt = parsed_args.prompt.strip()
        model = parsed_args.model.strip()
        output_filename = parsed_args.output_filename.strip()
        output_dir = parsed_args.output_dir.strip()
        size = _normalize_size(parsed_args.size)
    except ValueError as exc:
        return None, build_tool_error_result(
            "Argument validation failed",
            stage="validation",
            reason_code="ARGUMENT_VALIDATION_FAILED",
            category="validation",
            retryable=False,
            detail=str(exc),
            suggestion="Check argument types and value ranges, then try again",
        )

    if not prompt:
        return None, build_tool_error_result(
            "Argument validation failed",
            stage="validation",
            reason_code="MISSING_REQUIRED_ARGUMENT",
            category="validation",
            retryable=False,
            detail="Missing required argument: prompt",
            suggestion="Provide a non-empty prompt and try again",
        )

    if not model or not output_filename or not output_dir:
        return None, build_tool_error_result(
            "Argument validation failed",
            stage="validation",
            reason_code="ARGUMENT_VALIDATION_FAILED",
            category="validation",
            retryable=False,
            detail="model/output_filename/output_dir must be non-empty strings",
            suggestion="Check argument types and value ranges, then try again",
        )

    return (
        NormalizedGenerationArgs(
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
        ),
        None,
    )
