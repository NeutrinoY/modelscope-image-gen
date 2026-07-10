from __future__ import annotations

# pyright: reportAttributeAccessIssue=false
import httpx
from mcp import types

from ..payloads import (
    RETRYABLE_HTTP_STATUS,
    build_error_payload,
    build_tool_error_result,
    build_tool_success_result,
    parse_retry_after_seconds,
    stringify_body,
)


class ServiceStatusWorkflow:
    async def get_image_generation_status(self, *, job_id: str) -> types.CallToolResult:
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
            if not job.get("task_id"):
                return build_tool_error_result(
                    "Job state is invalid",
                    stage="validation",
                    reason_code="TASK_ID_MISSING",
                    category="validation",
                    retryable=False,
                    detail=f"job_id={job_id} does not contain task_id",
                    suggestion="Resubmit the generation request",
                )

            state = str(job.get("state", ""))
            if state in {"succeeded", "failed", "timeout", "canceled"}:
                return build_tool_success_result("Job status retrieved", data=self._build_job_data(job))

            self.settings.require_api_key()

            poll_cfg = job.get("poll", {}) if isinstance(job.get("poll"), dict) else {}
            base_interval = float(poll_cfg.get("base_interval", self.settings.modelscope_poll_interval_seconds))
            max_attempts = int(poll_cfg.get("max_attempts", self.settings.modelscope_max_poll_attempts))
            use_backoff = bool(poll_cfg.get("use_backoff", self.settings.modelscope_poll_backoff))
            max_interval = float(poll_cfg.get("max_interval", self.settings.modelscope_max_poll_interval_seconds))
            attempt = int(poll_cfg.get("attempt", 0)) + 1

            async with httpx.AsyncClient(timeout=60.0) as client:
                poll_response = await self.client.poll_task(client, task_id=str(job["task_id"]))

            poll_data = poll_response.json()
            task_status = str(poll_data.get("task_status", ""))
            request_id = poll_response.headers.get("X-Request-Id") or job.get("request_id")

            job["request_id"] = request_id
            job["provider_status"] = task_status
            job["poll"] = {
                "base_interval": base_interval,
                "max_attempts": max_attempts,
                "use_backoff": use_backoff,
                "max_interval": max_interval,
                "attempt": attempt,
            }
            job["recommended_wait_seconds"] = self._recommended_wait_seconds(
                base_interval=base_interval,
                use_backoff=use_backoff,
                attempt=attempt,
                max_interval=max_interval,
            )

            if task_status == "SUCCEED":
                output_images = poll_data.get("output_images", [])
                if output_images:
                    job["remote_image_url"] = output_images[0]
                    job["result_ready"] = True
                    job["state"] = "succeeded"
                    job["last_error"] = None
                else:
                    job["state"] = "failed"
                    job["last_error"] = build_error_payload(
                        stage="poll",
                        reason_code="EMPTY_OUTPUT_IMAGES",
                        category="upstream_response",
                        retryable=False,
                        request_id=request_id,
                        detail="task_status=SUCCEED but output_images is empty",
                        suggestion="Check model output and upstream response format",
                        body=poll_data,
                    )
            elif task_status == "FAILED":
                status_code = poll_data.get("status_code") or poll_data.get("code") or poll_response.status_code
                retryable = isinstance(status_code, int) and status_code in RETRYABLE_HTTP_STATUS
                job["state"] = "failed"
                job["result_ready"] = False
                job["last_error"] = build_error_payload(
                    stage="poll",
                    reason_code="TASK_FAILED",
                    category="upstream_task",
                    retryable=retryable,
                    retry_after_seconds=1 if retryable else None,
                    status_code=status_code if isinstance(status_code, int) else None,
                    request_id=request_id,
                    detail=str(poll_data.get("message") or "Task failed"),
                    suggestion="Adjust prompt, model, or request arguments based on upstream error details in body",
                    body=poll_data,
                )
            elif task_status in {"PENDING", "RUNNING", "PROCESSING"}:
                if attempt >= max_attempts:
                    job["state"] = "timeout"
                    job["result_ready"] = False
                    job["last_error"] = build_error_payload(
                        stage="poll",
                        reason_code="POLL_TIMEOUT",
                        category="timeout",
                        retryable=True,
                        retry_after_seconds=int(base_interval) if base_interval >= 1 else 1,
                        detail=(f"Task did not complete before max polling attempts: max_attempts={max_attempts}, base_interval={base_interval}, backoff={use_backoff}, max_interval={max_interval}"),
                        suggestion="Increase max_poll_attempts or check upstream queue/backlog status",
                    )
                else:
                    job["state"] = "in_progress"
            else:
                job["state"] = "failed"
                job["result_ready"] = False
                job["last_error"] = build_error_payload(
                    stage="poll",
                    reason_code="UNKNOWN_TASK_STATUS",
                    category="upstream_response",
                    retryable=False,
                    status_code=poll_response.status_code,
                    request_id=request_id,
                    detail=f"Received unrecognized task_status: {task_status}",
                    suggestion="Check for API version changes or task-status field compatibility changes",
                    body=poll_data,
                )

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

            return build_tool_success_result("Job status updated", data=self._build_job_data(job))
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
                stage="poll",
                reason_code="POLL_HTTP_ERROR",
                category="upstream_http",
                retryable=retryable,
                retry_after_seconds=retry_after_seconds,
                status_code=status_code,
                request_id=request_id,
                detail="Failed to query task status",
                suggestion="Retry status query later",
                body=body,
            )
        except httpx.RequestError as req_err:
            request_url = str(req_err.request.url) if req_err.request else None
            return build_tool_error_result(
                "Network request error",
                stage="poll",
                reason_code="NETWORK_ERROR",
                category="network",
                retryable=True,
                retry_after_seconds=1,
                detail=str(req_err),
                suggestion="Check network connectivity, DNS, proxy, and TLS settings",
                body=request_url,
            )
