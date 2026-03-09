from __future__ import annotations

# pyright: reportAttributeAccessIssue=false
import os

import httpx
from mcp import types

from ..payloads import (
    RETRYABLE_HTTP_STATUS,
    build_tool_error_result,
    build_tool_error_result_from_payload,
    build_tool_success_result,
    parse_retry_after_seconds,
    stringify_body,
)


class ServiceResultWorkflow:
    async def get_image_generation_result(self, *, job_id: str) -> types.CallToolResult:
        job, load_error = self._load_job_or_error(job_id=job_id)
        if load_error is not None:
            return load_error
        if job is None:
            return build_tool_error_result(
                "Job not found",
                stage="validation",
                reason_code="JOB_NOT_FOUND",
                category="validation",
                retryable=False,
                detail=f"No job found for job_id={job_id}",
                suggestion="Create a job first via submit_image_generation",
            )

        try:
            if bool(job.get("local_file_ready", False)) and os.path.exists(str(job.get("output_path", ""))):
                return build_tool_success_result("Image result is ready", data=self._build_job_data(job))

            state = str(job.get("state") or "")
            last_error = job.get("last_error")
            if state in {"failed", "timeout", "canceled"} and isinstance(last_error, dict):
                if state == "failed":
                    title = "Job failed"
                elif state == "timeout":
                    title = "Job timed out"
                else:
                    title = "Job was canceled"
                return build_tool_error_result_from_payload(title, payload=last_error)

            if not bool(job.get("result_ready", False)) or not job.get("remote_image_url"):
                return build_tool_error_result(
                    "Result is not ready",
                    stage="result",
                    reason_code="RESULT_NOT_READY",
                    category="state",
                    retryable=True,
                    retry_after_seconds=job.get("recommended_wait_seconds"),
                    detail=f"job_id={job_id} is currently in state {job.get('state')}",
                    suggestion="Call get_image_generation_status first to poll task status",
                    body={
                        "job_id": job_id,
                        "next_action": {
                            "tool": "get_image_generation_status",
                            "arguments": {"job_id": job_id},
                        },
                    },
                )

            self.settings.require_api_key()

            output_dir = str(job.get("output_dir") or "")
            output_path = str(job.get("output_path") or "")
            if output_dir:
                os.makedirs(output_dir, exist_ok=True)

            async with httpx.AsyncClient(timeout=60.0) as client:
                decode_phase = await self._download_decode_phase(client, image_url=str(job["remote_image_url"]))
            if isinstance(decode_phase, types.CallToolResult):
                return decode_phase
            image, _ = decode_phase

            save_error = self._save_image_phase(image=image, output_path=output_path)
            if save_error is not None:
                return save_error

            job["state"] = "succeeded"
            job["local_file_ready"] = True
            job["updated_at"] = self.task_store.now_iso()
            try:
                self.task_store.save(job)
            except RuntimeError as exc:
                return build_tool_error_result(
                    "Failed to persist job state",
                    stage="storage",
                    reason_code="JOB_STATE_WRITE_FAILED",
                    category="local_io",
                    retryable=False,
                    detail=str(exc),
                    suggestion="Check local job-state directory permissions and available disk space",
                )

            return build_tool_success_result("Image result saved", data=self._build_job_data(job))
        except ValueError as err:
            return build_tool_error_result(
                "Configuration error",
                stage="validation",
                reason_code="MISSING_API_KEY",
                category="validation",
                retryable=False,
                detail=str(err),
                suggestion="Set MODELSCOPE_SDK_TOKEN and try again",
            )
        except httpx.HTTPStatusError as http_err:
            resp = http_err.response
            status_code = getattr(resp, "status_code", None)
            request_id = resp.headers.get("X-Request-Id") if resp else None
            body = stringify_body(resp)
            retry_after_seconds = parse_retry_after_seconds(resp.headers.get("Retry-After") if resp else None)
            retryable = isinstance(status_code, int) and status_code in RETRYABLE_HTTP_STATUS
            return build_tool_error_result(
                "Request failed",
                stage="download",
                reason_code="DOWNLOAD_HTTP_ERROR",
                category="upstream_http",
                retryable=retryable,
                retry_after_seconds=retry_after_seconds,
                status_code=status_code,
                request_id=request_id,
                detail="Failed to download image",
                suggestion="Retry result retrieval later",
                body=body,
            )
        except httpx.RequestError as req_err:
            request_url = str(req_err.request.url) if req_err.request else None
            return build_tool_error_result(
                "Network request error",
                stage="download",
                reason_code="NETWORK_ERROR",
                category="network",
                retryable=True,
                retry_after_seconds=1,
                detail=str(req_err),
                suggestion="Check network connectivity, DNS, proxy, and TLS settings",
                body=request_url,
            )
