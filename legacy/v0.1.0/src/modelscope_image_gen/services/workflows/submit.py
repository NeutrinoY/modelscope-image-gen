from __future__ import annotations

# pyright: reportAttributeAccessIssue=false
import os

import httpx
from mcp import types

from ..payloads import RETRYABLE_HTTP_STATUS, build_tool_error_result, build_tool_success_result, parse_retry_after_seconds, stringify_body


class ServiceSubmitWorkflow:
    async def submit_image_generation(
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

            base_interval, max_attempts, use_backoff, max_interval = self._resolve_polling_config(
                poll_interval_seconds=poll_interval_seconds,
                max_poll_attempts=max_poll_attempts,
                poll_backoff=poll_backoff,
                max_poll_interval_seconds=max_poll_interval_seconds,
            )

            job_id = self.task_store.create_job_id()
            output_path = os.path.abspath(os.path.join(output_dir, output_filename))
            job_record = {
                "job_id": job_id,
                "state": "submitted",
                "provider_status": "SUBMITTED",
                "task_id": None,
                "request_id": None,
                "result_ready": False,
                "local_file_ready": False,
                "remote_image_url": None,
                "output_path": output_path,
                "output_dir": os.path.abspath(output_dir),
                "output_filename": output_filename,
                "prompt": prompt,
                "model": model,
                "size": size,
                "negative_prompt": negative_prompt,
                "seed": seed,
                "poll": {
                    "base_interval": base_interval,
                    "max_attempts": max_attempts,
                    "use_backoff": use_backoff,
                    "max_interval": max_interval,
                    "attempt": 0,
                },
                "recommended_wait_seconds": self._recommended_wait_seconds(
                    base_interval=base_interval,
                    use_backoff=use_backoff,
                    attempt=0,
                    max_interval=max_interval,
                ),
                "created_at": self.task_store.now_iso(),
                "updated_at": self.task_store.now_iso(),
            }

            async with httpx.AsyncClient(timeout=60.0) as client:
                submit_phase = await self._submit_generation_phase(
                    client,
                    model=model,
                    prompt=prompt,
                    size=size,
                    negative_prompt=negative_prompt,
                    seed=seed,
                )
            if isinstance(submit_phase, types.CallToolResult):
                return submit_phase

            task_id, submit_request_id = submit_phase
            job_record["task_id"] = task_id
            job_record["request_id"] = submit_request_id
            job_record["updated_at"] = self.task_store.now_iso()
            try:
                self.task_store.save(job_record)
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

            return build_tool_success_result("Job submitted. You can check status later.", data=self._build_job_data(job_record))
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
                stage="submit",
                reason_code="SUBMIT_HTTP_ERROR",
                category="upstream_http",
                retryable=retryable,
                retry_after_seconds=retry_after_seconds,
                status_code=status_code,
                request_id=request_id,
                detail="Upstream API returned a non-2xx status code",
                suggestion="Check request arguments, auth token, service availability, and use body/request_id for troubleshooting",
                body=body,
            )
        except httpx.RequestError as req_err:
            request_url = str(req_err.request.url) if req_err.request else None
            return build_tool_error_result(
                "Network request error",
                stage="submit",
                reason_code="NETWORK_ERROR",
                category="network",
                retryable=True,
                retry_after_seconds=1,
                detail=str(req_err),
                suggestion="Check network connectivity, DNS, proxy, and TLS settings",
                body=request_url,
            )
