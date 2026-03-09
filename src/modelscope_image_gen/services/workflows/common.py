from __future__ import annotations

# pyright: reportAttributeAccessIssue=false
from typing import Any

from mcp import types
from PIL import Image

from ..payloads import build_tool_error_result


class ServiceCommonWorkflow:
    settings: Any
    task_store: Any

    def _recommended_wait_seconds(self, *, base_interval: float, use_backoff: bool, attempt: int, max_interval: float) -> int:
        if not use_backoff:
            return int(base_interval) if base_interval >= 1 else 1
        wait_value = min(base_interval * (2 ** max(attempt, 0)), max_interval)
        return int(wait_value) if wait_value >= 1 else 1

    def _build_job_data(self, job: dict[str, Any], *, include_next_action: bool = True) -> dict[str, Any]:
        data: dict[str, Any] = {
            "job_id": job["job_id"],
            "state": job.get("state"),
            "is_terminal": str(job.get("state") or "") in {"succeeded", "failed", "timeout", "canceled"},
            "provider_status": job.get("provider_status"),
            "task_id": job.get("task_id"),
            "request_id": job.get("request_id"),
            "result_ready": bool(job.get("result_ready", False)),
            "local_file_ready": bool(job.get("local_file_ready", False)),
            "recommended_wait_seconds": job.get("recommended_wait_seconds"),
            "remote_image_url": job.get("remote_image_url"),
            "output_path": job.get("output_path"),
            "output_dir": job.get("output_dir"),
            "output_filename": job.get("output_filename"),
            "last_error": job.get("last_error"),
        }
        if include_next_action:
            state = str(job.get("state") or "")
            if state in {"submitted", "in_progress"}:
                data["next_action"] = {
                    "tool": "get_image_generation_status",
                    "arguments": {"job_id": job["job_id"]},
                }
            elif state == "succeeded" and not bool(job.get("local_file_ready", False)):
                data["next_action"] = {
                    "tool": "get_image_generation_result",
                    "arguments": {"job_id": job["job_id"]},
                }
        return data

    def _load_job_or_error(self, *, job_id: str) -> tuple[dict[str, Any] | None, types.CallToolResult | None]:
        try:
            job = self.task_store.load(job_id)
        except (RuntimeError, ValueError) as exc:
            return None, build_tool_error_result(
                "任务状态读取失败",
                stage="storage",
                reason_code="JOB_STATE_READ_FAILED",
                category="local_io",
                retryable=False,
                detail=str(exc),
                suggestion="检查本地任务状态目录权限与文件完整性",
            )
        if job is None:
            return None, build_tool_error_result(
                "任务不存在",
                stage="validation",
                reason_code="JOB_NOT_FOUND",
                category="validation",
                retryable=False,
                detail=f"未找到 job_id={job_id}",
                suggestion="先调用 submit_image_generation 创建任务",
            )
        return job, None

    def _resolve_polling_config(
        self,
        *,
        poll_interval_seconds: float | None,
        max_poll_attempts: int | None,
        poll_backoff: bool | None,
        max_poll_interval_seconds: float | None,
    ) -> tuple[float, int, bool, float]:
        cfg = self.settings.polling_defaults()
        base_interval = poll_interval_seconds if poll_interval_seconds is not None else float(cfg["base_interval"])
        max_attempts = max_poll_attempts if max_poll_attempts is not None else int(cfg["max_attempts"])
        use_backoff = poll_backoff if poll_backoff is not None else bool(cfg["backoff"])
        max_interval = max_poll_interval_seconds if max_poll_interval_seconds is not None else float(cfg["max_interval"])
        return base_interval, max_attempts, use_backoff, max_interval

    def _save_image_phase(self, *, image: Image.Image, output_path: str) -> types.CallToolResult | None:
        try:
            if output_path.lower().endswith((".jpg", ".jpeg")) and image.mode in ("RGBA", "P"):
                image = image.convert("RGB")
            image.save(output_path)
            return None
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
