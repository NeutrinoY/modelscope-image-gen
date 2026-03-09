from __future__ import annotations

# pyright: reportMissingImports=false
import asyncio
import logging
import os
from io import BytesIO
from typing import Any

import httpx
from mcp import types
from PIL import Image, UnidentifiedImageError

from .client import ModelScopeClient
from .config import Settings

logger = logging.getLogger("modelscope-image-gen")

_RETRYABLE_HTTP_STATUS = {408, 409, 425, 429, 500, 502, 503, 504}
_SENSITIVE_KEYS = {
    "authorization",
    "api_key",
    "apikey",
    "token",
    "access_token",
    "refresh_token",
    "password",
    "secret",
    "cookie",
    "set-cookie",
    "modelscope_sdk_token",
}


def _redact_text(value: str) -> str:
    lower = value.lower()
    markers = ["token=", "api_key=", "apikey=", "password="]
    for marker in markers:
        idx = lower.find(marker)
        if idx == -1:
            continue
        start = idx + len(marker)
        end = value.find("&", start)
        if end == -1:
            end = len(value)
        value = value[:start] + "[REDACTED]" + value[end:]
        lower = value.lower()

    if "bearer " in lower:
        parts = value.split("Bearer ")
        if len(parts) >= 2:
            first = parts[0]
            tail = []
            for p in parts[1:]:
                token_end = p.find(" ")
                if token_end == -1:
                    tail.append("[REDACTED]")
                else:
                    tail.append("[REDACTED]" + p[token_end:])
            value = first + "Bearer ".join(tail)

    return value


def _redact_data(value: Any) -> Any:
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, val in value.items():
            if str(key).lower() in _SENSITIVE_KEYS:
                out[str(key)] = "[REDACTED]"
            else:
                out[str(key)] = _redact_data(val)
        return out
    if isinstance(value, list):
        return [_redact_data(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_redact_data(item) for item in value)
    if isinstance(value, str):
        return _redact_text(value)
    return value


def _parse_retry_after_seconds(value: str | None) -> int | None:
    if not value:
        return None
    try:
        seconds = int(value.strip())
        return seconds if seconds >= 0 else None
    except ValueError:
        return None


def _stringify_body(response: httpx.Response | None) -> str | None:
    if response is None:
        return None
    try:
        return str(_redact_data(response.text))
    except Exception:  # noqa: BLE001
        return None


def _build_error_payload(
    *,
    stage: str,
    reason_code: str,
    category: str,
    retryable: bool,
    retry_after_seconds: int | None = None,
    status_code: int | None = None,
    request_id: str | None = None,
    detail: str | None = None,
    suggestion: str | None = None,
    body: Any | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "stage": stage,
        "reason_code": reason_code,
        "category": category,
        "retryable": retryable,
        "retry_after_seconds": retry_after_seconds,
    }
    if status_code is not None:
        payload["status_code"] = status_code
    if request_id:
        payload["request_id"] = request_id
    if detail:
        payload["detail"] = str(_redact_data(detail))
    if suggestion:
        payload["suggestion"] = suggestion
    if body is not None:
        payload["body"] = _redact_data(body)
    return payload


def _build_error_text(title: str, payload: dict[str, Any]) -> str:
    lines = [
        title,
        f"stage: {payload['stage']}",
        f"reason_code: {payload['reason_code']}",
        f"category: {payload['category']}",
        f"retryable: {payload['retryable']}",
    ]
    if payload.get("retry_after_seconds") is not None:
        lines.append(f"retry_after_seconds: {payload['retry_after_seconds']}")

    for field in ["status_code", "request_id", "detail", "suggestion", "body"]:
        if field in payload and payload[field] is not None:
            lines.append(f"{field}: {payload[field]}")
    return "\n".join(lines)


def build_tool_error_result(title: str, **kwargs: Any) -> types.CallToolResult:
    payload = _build_error_payload(**kwargs)
    return types.CallToolResult(
        isError=True,
        content=[types.TextContent(type="text", text=_build_error_text(title, payload))],
        structuredContent={"ok": False, "error": payload},
    )


def build_tool_success_result(message: str, data: dict[str, Any]) -> types.CallToolResult:
    return types.CallToolResult(
        isError=False,
        content=[types.TextContent(type="text", text=message)],
        structuredContent={"ok": True, "data": data},
    )


class ImageGenerationService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = ModelScopeClient(
            api_base=settings.modelscope_api_base,
            api_key=settings.modelscope_sdk_token,
        )

    async def generate_image(
        self,
        *,
        prompt: str,
        model: str,
        size: str,
        output_filename: str,
        output_dir: str,
        poll_interval_seconds: float | None,
        max_poll_attempts: int | None,
        poll_backoff: bool | None,
        max_poll_interval_seconds: float | None,
        negative_prompt: str | None,
        seed: int | None,
    ) -> types.CallToolResult:
        try:
            self.settings.require_api_key()
            os.makedirs(output_dir, exist_ok=True)
            output_path = os.path.join(output_dir, output_filename)

            cfg = self.settings.polling_defaults()
            base_interval = poll_interval_seconds if poll_interval_seconds is not None else float(cfg["base_interval"])
            max_attempts = max_poll_attempts if max_poll_attempts is not None else int(cfg["max_attempts"])
            use_backoff = poll_backoff if poll_backoff is not None else bool(cfg["backoff"])
            max_interval = max_poll_interval_seconds if max_poll_interval_seconds is not None else float(cfg["max_interval"])

            logger.info("正在使用模型 %s 生成图片，提示词: %s", model, prompt)

            async with httpx.AsyncClient(timeout=60.0) as client:
                submit_response = await self.client.submit_generation(
                    client,
                    model=model,
                    prompt=prompt,
                    size=size,
                    negative_prompt=negative_prompt,
                    seed=seed,
                )
                submit_data = submit_response.json()
                task_id = submit_data.get("task_id")
                submit_request_id = submit_response.headers.get("X-Request-Id")
                if not task_id:
                    return build_tool_error_result(
                        "任务提交失败",
                        stage="submit",
                        reason_code="TASK_ID_MISSING",
                        category="upstream_response",
                        retryable=True,
                        retry_after_seconds=1,
                        status_code=submit_response.status_code,
                        request_id=submit_request_id,
                        detail="提交成功返回，但响应中缺少 task_id",
                        suggestion="检查模型与参数是否被服务端接受，确认网关是否返回标准异步任务结构",
                        body=submit_data,
                    )

                attempt = 0
                while attempt < max_attempts:
                    wait_time = base_interval if not use_backoff else min(base_interval * (2**attempt), max_interval)
                    await asyncio.sleep(wait_time)
                    attempt += 1

                    poll_response = await self.client.poll_task(client, task_id=task_id)
                    poll_data = poll_response.json()
                    task_status = poll_data.get("task_status")
                    poll_request_id = poll_response.headers.get("X-Request-Id")
                    logger.info("任务状态: %s (尝试 %s/%s, wait=%.2fs)", task_status, attempt, max_attempts, wait_time)

                    if task_status == "SUCCEED":
                        output_images = poll_data.get("output_images", [])
                        if not output_images:
                            return build_tool_error_result(
                                "任务成功但没有输出图片",
                                stage="poll",
                                reason_code="EMPTY_OUTPUT_IMAGES",
                                category="upstream_response",
                                retryable=False,
                                request_id=poll_request_id or submit_request_id,
                                detail="task_status=SUCCEED 但 output_images 为空",
                                suggestion="检查模型输出内容与服务端返回格式",
                                body=poll_data,
                            )

                        image_url = output_images[0]
                        image_response = await self.client.download_image(client, image_url=image_url)
                        image_request_id = image_response.headers.get("X-Request-Id")
                        content_type = image_response.headers.get("Content-Type", "")
                        if not content_type.startswith("image/"):
                            return build_tool_error_result(
                                "图片下载失败：返回的内容不是图片",
                                stage="download",
                                reason_code="INVALID_CONTENT_TYPE",
                                category="upstream_response",
                                retryable=False,
                                status_code=image_response.status_code,
                                request_id=image_request_id,
                                detail=f"下载内容的 Content-Type 为 {content_type}",
                                suggestion="检查返回 URL 是否过期、鉴权是否生效、或服务端是否返回了错误页面",
                            )

                        try:
                            image = Image.open(BytesIO(image_response.content))
                        except UnidentifiedImageError:
                            return build_tool_error_result(
                                "图片解析失败",
                                stage="decode",
                                reason_code="IMAGE_DECODE_FAILED",
                                category="data_format",
                                retryable=False,
                                status_code=image_response.status_code,
                                request_id=image_request_id,
                                detail="Content-Type 为图片，但 PIL 无法解析字节内容",
                                suggestion="检查返回数据是否损坏，或服务端是否返回了非标准图片字节",
                            )

                        try:
                            if output_path.lower().endswith((".jpg", ".jpeg")) and image.mode in ("RGBA", "P"):
                                image = image.convert("RGB")
                            image.save(output_path)
                        except Exception as save_err:  # noqa: BLE001
                            return build_tool_error_result(
                                "图片保存失败",
                                stage="save",
                                reason_code="IMAGE_SAVE_FAILED",
                                category="local_io",
                                retryable=False,
                                detail=str(save_err),
                                suggestion="检查输出目录权限、磁盘空间、文件名是否合法",
                            )

                        message = (
                            "图片生成成功！\n"
                            f"提示词: {prompt}\n"
                            f"模型: {model}\n"
                            f"分辨率: {size}\n"
                            f"保存路径: {os.path.abspath(output_path)}\n"
                            f"输出目录: {os.path.abspath(output_dir)}\n"
                            f"文件名: {output_filename}\n"
                            f"图片URL: {image_url}\n"
                            f"request_id: {poll_request_id or submit_request_id}"
                        )
                        return build_tool_success_result(
                            message,
                            data={
                                "prompt": prompt,
                                "model": model,
                                "size": size,
                                "output_path": os.path.abspath(output_path),
                                "output_dir": os.path.abspath(output_dir),
                                "output_filename": output_filename,
                                "image_url": image_url,
                                "request_id": poll_request_id or submit_request_id,
                            },
                        )

                    if task_status == "FAILED":
                        error_msg = poll_data.get("message", "任务失败")
                        status_code = poll_data.get("status_code") or poll_data.get("code") or poll_response.status_code
                        retryable = isinstance(status_code, int) and status_code in _RETRYABLE_HTTP_STATUS
                        return build_tool_error_result(
                            "图片生成失败",
                            stage="poll",
                            reason_code="TASK_FAILED",
                            category="upstream_task",
                            retryable=retryable,
                            retry_after_seconds=1 if retryable else None,
                            status_code=status_code if isinstance(status_code, int) else None,
                            request_id=poll_request_id,
                            detail=error_msg,
                            suggestion="根据 body 中的服务端错误信息调整提示词、模型或请求参数",
                            body=poll_data,
                        )

                    if task_status not in {"PENDING", "RUNNING"}:
                        return build_tool_error_result(
                            "任务状态异常",
                            stage="poll",
                            reason_code="UNKNOWN_TASK_STATUS",
                            category="upstream_response",
                            retryable=False,
                            status_code=poll_response.status_code,
                            request_id=poll_request_id,
                            detail=f"收到未识别的 task_status: {task_status}",
                            suggestion="检查 API 版本是否变化，或任务状态字段是否发生兼容性变更",
                            body=poll_data,
                        )

                return build_tool_error_result(
                    "图片生成超时，任务可能仍在处理中",
                    stage="poll",
                    reason_code="POLL_TIMEOUT",
                    category="timeout",
                    retryable=True,
                    retry_after_seconds=int(base_interval) if base_interval >= 1 else 1,
                    detail=(
                        f"达到最大轮询次数仍未完成: max_attempts={max_attempts}, "
                        f"base_interval={base_interval}, backoff={use_backoff}, max_interval={max_interval}"
                    ),
                    suggestion="适当提高 max_poll_attempts 或检查服务端任务排队情况",
                )
        except ValueError as err:
            return build_tool_error_result(
                "配置错误",
                stage="validation",
                reason_code="MISSING_API_KEY",
                category="validation",
                retryable=False,
                detail=str(err),
                suggestion="设置环境变量 MODELSCOPE_SDK_TOKEN 后重试",
            )
        except httpx.HTTPStatusError as http_err:
            resp = http_err.response
            status_code = getattr(resp, "status_code", None)
            request_id = resp.headers.get("X-Request-Id") if resp else None
            body = _stringify_body(resp)
            retry_after_seconds = _parse_retry_after_seconds(resp.headers.get("Retry-After") if resp else None)

            stage = "request"
            reason_code = "HTTP_STATUS_ERROR"
            if resp is not None and resp.request is not None:
                path = resp.request.url.path
                if path.endswith("/v1/images/generations"):
                    stage = "submit"
                    reason_code = "SUBMIT_HTTP_ERROR"
                elif "/v1/tasks/" in path:
                    stage = "poll"
                    reason_code = "POLL_HTTP_ERROR"
                else:
                    stage = "download"
                    reason_code = "DOWNLOAD_HTTP_ERROR"

            retryable = isinstance(status_code, int) and status_code in _RETRYABLE_HTTP_STATUS
            return build_tool_error_result(
                "请求失败",
                stage=stage,
                reason_code=reason_code,
                category="upstream_http",
                retryable=retryable,
                retry_after_seconds=retry_after_seconds,
                status_code=status_code,
                request_id=request_id,
                detail="上游接口返回非 2xx 状态码",
                suggestion="检查请求参数、鉴权令牌、服务可用性，并结合 body 与 request_id 排查",
                body=body,
            )
        except httpx.RequestError as req_err:
            request_url = str(req_err.request.url) if req_err.request else None
            return build_tool_error_result(
                "网络请求异常",
                stage="request",
                reason_code="NETWORK_ERROR",
                category="network",
                retryable=True,
                retry_after_seconds=1,
                detail=str(req_err),
                suggestion="检查网络连通性、DNS、代理与 TLS 配置",
                body=request_url,
            )
        except Exception as err:  # noqa: BLE001
            return build_tool_error_result(
                "生成图片时发生错误",
                stage="unexpected",
                reason_code="UNEXPECTED_ERROR",
                category="internal",
                retryable=False,
                detail=str(err),
                suggestion="查看服务端日志并携带请求参数进行复现",
            )
