from __future__ import annotations

# pyright: reportMissingImports=false, reportAttributeAccessIssue=false
import asyncio
import logging
from io import BytesIO
from typing import Any

import httpx
from mcp import types
from PIL import Image, UnidentifiedImageError

from ..payloads import RETRYABLE_HTTP_STATUS, build_tool_error_result

logger = logging.getLogger("modelscope-image-gen")


class ServicePhaseWorkflow:
    client: Any

    async def _submit_generation_phase(
        self,
        client: httpx.AsyncClient,
        *,
        model: str,
        prompt: str,
        size: str,
        negative_prompt: str | None,
        seed: int | None,
    ) -> tuple[str, str | None] | types.CallToolResult:
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
        logger.info("stage=submit request_id=%s task_id=%s", submit_request_id, task_id)
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
        return task_id, submit_request_id

    async def _poll_generation_phase(
        self,
        client: httpx.AsyncClient,
        *,
        task_id: str,
        submit_request_id: str | None,
        base_interval: float,
        max_attempts: int,
        use_backoff: bool,
        max_interval: float,
    ) -> tuple[str, str | None] | types.CallToolResult:
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
            logger.info(
                "stage=poll request_id=%s task_id=%s status=%s attempt=%s/%s",
                poll_request_id,
                task_id,
                task_status,
                attempt,
                max_attempts,
            )

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
                return output_images[0], poll_request_id

            if task_status == "FAILED":
                error_msg = poll_data.get("message", "任务失败")
                status_code = poll_data.get("status_code") or poll_data.get("code") or poll_response.status_code
                retryable = isinstance(status_code, int) and status_code in RETRYABLE_HTTP_STATUS
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

            if task_status not in {"PENDING", "RUNNING", "PROCESSING"}:
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
            detail=(f"达到最大轮询次数仍未完成: max_attempts={max_attempts}, base_interval={base_interval}, backoff={use_backoff}, max_interval={max_interval}"),
            suggestion="适当提高 max_poll_attempts 或检查服务端任务排队情况",
        )

    async def _download_decode_phase(
        self,
        client: httpx.AsyncClient,
        *,
        image_url: str,
    ) -> tuple[Image.Image, str | None] | types.CallToolResult:
        image_response = await self.client.download_image(client, image_url=image_url)
        image_request_id = image_response.headers.get("X-Request-Id")
        content_type = image_response.headers.get("Content-Type", "")
        normalized_content_type = content_type.split(";", 1)[0].strip().lower()
        logger.info("stage=download request_id=%s image_url=%s", image_request_id, image_url)
        if normalized_content_type and normalized_content_type != "application/octet-stream" and not normalized_content_type.startswith("image/"):
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
        return image, image_request_id
