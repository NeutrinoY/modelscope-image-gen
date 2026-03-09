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
                "任务不存在",
                stage="validation",
                reason_code="JOB_NOT_FOUND",
                category="validation",
                retryable=False,
                detail=f"未找到 job_id={job_id}",
                suggestion="先调用 submit_image_generation 创建任务",
            )

        try:
            if bool(job.get("local_file_ready", False)) and os.path.exists(str(job.get("output_path", ""))):
                return build_tool_success_result("图片结果已就绪", data=self._build_job_data(job))

            state = str(job.get("state") or "")
            last_error = job.get("last_error")
            if state in {"failed", "timeout", "canceled"} and isinstance(last_error, dict):
                title = "任务已失败" if state == "failed" else "任务未完成"
                return build_tool_error_result_from_payload(title, payload=last_error)

            if not bool(job.get("result_ready", False)) or not job.get("remote_image_url"):
                return build_tool_error_result(
                    "结果尚未就绪",
                    stage="result",
                    reason_code="RESULT_NOT_READY",
                    category="state",
                    retryable=True,
                    retry_after_seconds=job.get("recommended_wait_seconds"),
                    detail=f"job_id={job_id} 当前状态为 {job.get('state')}",
                    suggestion="先调用 get_image_generation_status 轮询任务状态",
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
                    "任务状态保存失败",
                    stage="storage",
                    reason_code="JOB_STATE_WRITE_FAILED",
                    category="local_io",
                    retryable=False,
                    detail=str(exc),
                    suggestion="检查本地任务状态目录权限与磁盘空间",
                )

            return build_tool_success_result("图片结果已保存", data=self._build_job_data(job))
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
                stage="download",
                reason_code="DOWNLOAD_HTTP_ERROR",
                category="upstream_http",
                retryable=retryable,
                retry_after_seconds=retry_after_seconds,
                status_code=status_code,
                request_id=request_id,
                detail="图片下载失败",
                suggestion="稍后重试获取结果",
                body=body,
            )
        except httpx.RequestError as req_err:
            request_url = str(req_err.request.url) if req_err.request else None
            return build_tool_error_result(
                "网络请求异常",
                stage="download",
                reason_code="NETWORK_ERROR",
                category="network",
                retryable=True,
                retry_after_seconds=1,
                detail=str(req_err),
                suggestion="检查网络连通性、DNS、代理与 TLS 配置",
                body=request_url,
            )
