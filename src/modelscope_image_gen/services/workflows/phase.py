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
                "Job submission failed",
                stage="submit",
                reason_code="TASK_ID_MISSING",
                category="upstream_response",
                retryable=True,
                retry_after_seconds=1,
                status_code=submit_response.status_code,
                request_id=submit_request_id,
                detail="Submission returned success but task_id is missing in the response",
                suggestion="Check whether the model and arguments are accepted and whether the gateway returns the standard async task schema",
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
            logger.info(
                "stage=poll status=%s attempt=%s/%s wait=%.2fs task_id=%s",
                task_status,
                attempt,
                max_attempts,
                wait_time,
                task_id,
            )
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
                        "Task succeeded but no output image was returned",
                        stage="poll",
                        reason_code="EMPTY_OUTPUT_IMAGES",
                        category="upstream_response",
                        retryable=False,
                        request_id=poll_request_id or submit_request_id,
                        detail="task_status=SUCCEED but output_images is empty",
                        suggestion="Check model output and upstream response format",
                        body=poll_data,
                    )
                return output_images[0], poll_request_id

            if task_status == "FAILED":
                error_msg = poll_data.get("message", "Task failed")
                status_code = poll_data.get("status_code") or poll_data.get("code") or poll_response.status_code
                retryable = isinstance(status_code, int) and status_code in RETRYABLE_HTTP_STATUS
                return build_tool_error_result(
                    "Image generation failed",
                    stage="poll",
                    reason_code="TASK_FAILED",
                    category="upstream_task",
                    retryable=retryable,
                    retry_after_seconds=1 if retryable else None,
                    status_code=status_code if isinstance(status_code, int) else None,
                    request_id=poll_request_id,
                    detail=error_msg,
                    suggestion="Adjust prompt, model, or request arguments based on upstream error details in body",
                    body=poll_data,
                )

            if task_status not in {"PENDING", "RUNNING", "PROCESSING"}:
                return build_tool_error_result(
                    "Unexpected task status",
                    stage="poll",
                    reason_code="UNKNOWN_TASK_STATUS",
                    category="upstream_response",
                    retryable=False,
                    status_code=poll_response.status_code,
                    request_id=poll_request_id,
                    detail=f"Received unrecognized task_status: {task_status}",
                    suggestion="Check for API version changes or task-status field compatibility changes",
                    body=poll_data,
                )

        return build_tool_error_result(
            "Image generation timed out; the task may still be processing",
            stage="poll",
            reason_code="POLL_TIMEOUT",
            category="timeout",
            retryable=True,
            retry_after_seconds=int(base_interval) if base_interval >= 1 else 1,
            detail=(f"Task did not complete before max polling attempts: max_attempts={max_attempts}, base_interval={base_interval}, backoff={use_backoff}, max_interval={max_interval}"),
            suggestion="Increase max_poll_attempts or check upstream queue/backlog status",
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
                "Image download failed: response is not an image",
                stage="download",
                reason_code="INVALID_CONTENT_TYPE",
                category="upstream_response",
                retryable=False,
                status_code=image_response.status_code,
                request_id=image_request_id,
                detail=f"Downloaded content has Content-Type: {content_type}",
                suggestion="Check whether the URL expired, authentication is valid, or the server returned an error page",
            )

        try:
            image = Image.open(BytesIO(image_response.content))
        except UnidentifiedImageError:
            return build_tool_error_result(
                "Image decode failed",
                stage="decode",
                reason_code="IMAGE_DECODE_FAILED",
                category="data_format",
                retryable=False,
                status_code=image_response.status_code,
                request_id=image_request_id,
                detail="Content-Type indicates an image, but PIL cannot decode the bytes",
                suggestion="Check whether returned bytes are corrupted or in a non-standard image format",
            )
        return image, image_request_id
