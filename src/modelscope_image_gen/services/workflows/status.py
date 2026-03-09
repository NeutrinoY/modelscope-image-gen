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
                "任务不存在",
                stage="validation",
                reason_code="JOB_NOT_FOUND",
                category="validation",
                retryable=False,
                detail=f"未找到 job_id={job_id}",
                suggestion="先调用 submit_image_generation 创建任务",
            )

        try:
            if not job.get("task_id"):
                return build_tool_error_result(
                    "任务状态异常",
                    stage="validation",
                    reason_code="TASK_ID_MISSING",
                    category="validation",
                    retryable=False,
                    detail=f"job_id={job_id} 未记录 task_id",
                    suggestion="重新提交任务",
                )

            state = str(job.get("state", ""))
            if state in {"succeeded", "failed", "timeout", "canceled"}:
                return build_tool_success_result("任务状态已就绪", data=self._build_job_data(job))

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
                        detail="task_status=SUCCEED 但 output_images 为空",
                        suggestion="检查模型输出内容与服务端返回格式",
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
                    detail=str(poll_data.get("message") or "任务失败"),
                    suggestion="根据 body 中的服务端错误信息调整提示词、模型或请求参数",
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
                        detail=(f"达到最大轮询次数仍未完成: max_attempts={max_attempts}, base_interval={base_interval}, backoff={use_backoff}, max_interval={max_interval}"),
                        suggestion="适当提高 max_poll_attempts 或检查服务端任务排队情况",
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
                    detail=f"收到未识别的 task_status: {task_status}",
                    suggestion="检查 API 版本是否变化，或任务状态字段是否发生兼容性变更",
                    body=poll_data,
                )

            job["updated_at"] = self.task_store.now_iso()
            try:
                self.task_store.save(job)
            except RuntimeError as exc:
                return build_tool_error_result(
                    "任务状态保存失败",
                    stage="storage",
                    reason_code="JOB_STATE_WRITE_FAILED",
                    category="local_io",
                    retryable=False,
                    detail=str(exc),
                    suggestion="检查本地任务状态目录权限与磁盘空间",
                )

            return build_tool_success_result("任务状态已更新", data=self._build_job_data(job))
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
            body = stringify_body(resp)
            retry_after_seconds = parse_retry_after_seconds(resp.headers.get("Retry-After") if resp else None)
            retryable = isinstance(status_code, int) and status_code in RETRYABLE_HTTP_STATUS
            return build_tool_error_result(
                "请求失败",
                stage="poll",
                reason_code="POLL_HTTP_ERROR",
                category="upstream_http",
                retryable=retryable,
                retry_after_seconds=retry_after_seconds,
                status_code=status_code,
                request_id=request_id,
                detail="任务状态查询失败",
                suggestion="稍后重试状态查询",
                body=body,
            )
        except httpx.RequestError as req_err:
            request_url = str(req_err.request.url) if req_err.request else None
            return build_tool_error_result(
                "网络请求异常",
                stage="poll",
                reason_code="NETWORK_ERROR",
                category="network",
                retryable=True,
                retry_after_seconds=1,
                detail=str(req_err),
                suggestion="检查网络连通性、DNS、代理与 TLS 配置",
                body=request_url,
            )
