from __future__ import annotations

import logging
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path

from modelscope_image_gen.domain import JobId

logger = logging.getLogger("modelscope-image-gen-mcp")


def clean_temporary_files(artifact_root: Path, *, retention_hours: int) -> int:
    cutoff = datetime.now(UTC) - timedelta(hours=retention_hours)
    removed = 0
    jobs = artifact_root / "jobs"
    if not jobs.exists():
        return 0
    for path in jobs.glob("*/.tmp/*.part"):
        try:
            modified = datetime.fromtimestamp(path.stat().st_mtime, UTC)
            if modified < cutoff:
                path.unlink(missing_ok=True)
                removed += 1
        except OSError:
            logger.warning("temp_cleanup_failed")
    return removed


def delete_relative_job_directory(artifact_root: Path, relative_job_dir: str) -> None:
    parts = relative_job_dir.replace("\\", "/").split("/")
    if len(parts) != 2 or parts[0] != "jobs":
        raise ValueError("invalid cleanup path")
    JobId(parts[1])
    root = artifact_root.resolve()
    candidate = root
    for part in parts:
        candidate /= part
        if candidate.exists() and (candidate.is_symlink() or candidate.is_junction()):
            raise ValueError("cleanup path contains a link or reparse point")
    candidate = candidate.resolve()
    if not candidate.is_relative_to(root):
        raise ValueError("cleanup path escapes artifact root")
    if candidate.exists():
        shutil.rmtree(candidate)
