from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from tempfile import NamedTemporaryFile
from typing import Any


class TaskStore:
    def __init__(self, *, state_dir: str) -> None:
        self.state_dir = state_dir

    def ensure_dir(self) -> None:
        os.makedirs(self.state_dir, exist_ok=True)

    def now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()  # noqa: UP017

    def create_job_id(self) -> str:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")  # noqa: UP017
        return f"job_{stamp}"

    def _job_path(self, job_id: str) -> str:
        safe_id = "".join(ch for ch in job_id if ch.isalnum() or ch in {"_", "-"})
        if safe_id != job_id or not safe_id:
            raise ValueError("invalid job_id")
        return os.path.join(self.state_dir, f"{safe_id}.json")

    def load(self, job_id: str) -> dict[str, Any] | None:
        path = self._job_path(job_id)
        if not os.path.exists(path):
            return None
        try:
            with open(path, encoding="utf-8") as fp:
                data = json.load(fp)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"job state file is corrupted: {path}") from exc
        except OSError as exc:
            raise RuntimeError(f"failed to read job state file: {path}") from exc
        if not isinstance(data, dict):
            raise RuntimeError(f"job state file has invalid format: {path}")
        return data

    def save(self, payload: dict[str, Any]) -> dict[str, Any]:
        job_id = str(payload.get("job_id", "")).strip()
        if not job_id:
            raise ValueError("job_id is required")

        self.ensure_dir()
        path = self._job_path(job_id)

        try:
            with NamedTemporaryFile("w", delete=False, encoding="utf-8", dir=self.state_dir) as tmp:
                json.dump(payload, tmp, ensure_ascii=False, indent=2)
                tmp.flush()
                os.fsync(tmp.fileno())
                temp_path = tmp.name

            os.replace(temp_path, path)
        except OSError as exc:
            raise RuntimeError(f"failed to write job state file: {path}") from exc
        return payload
