from __future__ import annotations

import base64
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid7

import aiosqlite

from modelscope_image_gen.application.repositories import (
    JobListQuery,
    StoredGenerationJob,
    StoredJobPage,
)
from modelscope_image_gen.domain import (
    ArtifactKey,
    ArtifactStatus,
    DomainError,
    ErrorCategory,
    ErrorCode,
    ErrorStage,
    GeneratedImage,
    GenerationJob,
    GenerationRequest,
    ImageId,
    ImageSize,
    JobId,
    JobStatus,
    LocalArtifact,
    ProviderImageReference,
    ProviderTaskReference,
)

SCHEMA_VERSION = 1


class SqliteGenerationJobRepository:
    def __init__(self, connection: aiosqlite.Connection, artifact_root: Path) -> None:
        self._db = connection
        self._artifact_root = artifact_root.resolve()

    @classmethod
    async def open(cls, database_path: Path, *, artifact_root: Path) -> SqliteGenerationJobRepository:
        database_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_root.mkdir(parents=True, exist_ok=True)
        db = await aiosqlite.connect(database_path)
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys = ON")
        await db.execute("PRAGMA journal_mode = WAL")
        await db.execute("PRAGMA synchronous = NORMAL")
        await db.execute("PRAGMA busy_timeout = 5000")
        row = await (await db.execute("PRAGMA user_version")).fetchone()
        if row is None:
            await db.close()
            raise RuntimeError("could not read SQLite schema version")
        version = int(row[0])
        if version > SCHEMA_VERSION:
            await db.close()
            raise RuntimeError(f"database schema version {version} is newer than supported version {SCHEMA_VERSION}")
        if version == 0:
            script = (Path(__file__).parent / "migrations" / "v001_initial.sql").read_text(encoding="utf-8")
            await db.executescript(script)
            await db.commit()
        return cls(db, artifact_root)

    async def close(self) -> None:
        await self._db.close()

    async def add(self, job: GenerationJob) -> StoredGenerationJob:
        values = _job_values(job, revision=0)
        columns = ", ".join(values)
        placeholders = ", ".join("?" for _ in values)
        try:
            await self._db.execute("BEGIN IMMEDIATE")
            await self._db.execute(
                f"INSERT INTO generation_jobs ({columns}) VALUES ({placeholders})", tuple(values.values())
            )
            await self._replace_images(job)
            await self._db.commit()
        except Exception:
            await self._db.rollback()
            raise
        return StoredGenerationJob(job, 0)

    async def get(self, job_id: JobId) -> StoredGenerationJob | None:
        row = await (
            await self._db.execute("SELECT * FROM generation_jobs WHERE job_id = ?", (str(job_id),))
        ).fetchone()
        if row is None:
            return None
        images = await self._load_images(str(job_id))
        return StoredGenerationJob(_row_to_job(row, images, self._artifact_root), int(row["revision"]))

    async def save(self, job: GenerationJob, *, expected_revision: int) -> StoredGenerationJob:
        next_revision = expected_revision + 1
        values = _job_values(job, revision=next_revision)
        assignments = ", ".join(f"{name} = ?" for name in values if name != "job_id")
        params = (
            *(value for name, value in values.items() if name != "job_id"),
            str(job.job_id),
            expected_revision,
        )
        try:
            await self._db.execute("BEGIN IMMEDIATE")
            cursor = await self._db.execute(
                f"UPDATE generation_jobs SET {assignments} WHERE job_id = ? AND revision = ?",
                params,
            )
            if cursor.rowcount != 1:
                raise RuntimeError("CONCURRENT_MODIFICATION: generation job revision changed")
            await self._replace_images(job)
            await self._db.commit()
        except Exception:
            await self._db.rollback()
            raise
        return StoredGenerationJob(job, next_revision)

    async def list(self, query: JobListQuery) -> StoredJobPage:
        statuses = tuple(sorted({status.value for status in query.statuses})) if query.statuses else ()
        fingerprint = hashlib.sha256(",".join(statuses).encode()).hexdigest()[:16]
        cursor_values: tuple[str, str] | None = None
        if query.cursor:
            cursor_values = _decode_cursor(query.cursor, fingerprint)
        where: list[str] = []
        params: list[Any] = []
        if statuses:
            where.append(f"status IN ({','.join('?' for _ in statuses)})")
            params.extend(statuses)
        if cursor_values:
            where.append("(updated_at < ? OR (updated_at = ? AND job_id < ?))")
            params.extend((cursor_values[0], cursor_values[0], cursor_values[1]))
        sql = "SELECT * FROM generation_jobs"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY updated_at DESC, job_id DESC LIMIT ?"
        params.append(query.limit + 1)
        rows = tuple(await (await self._db.execute(sql, tuple(params))).fetchall())
        has_more = len(rows) > query.limit
        rows = rows[: query.limit]
        items: list[StoredGenerationJob] = []
        for row in rows:
            images = await self._load_images(row["job_id"])
            items.append(StoredGenerationJob(_row_to_job(row, images, self._artifact_root), int(row["revision"])))
        next_cursor = None
        if has_more and rows:
            last = rows[-1]
            next_cursor = _encode_cursor(last["updated_at"], last["job_id"], fingerprint)
        return StoredJobPage(tuple(items), next_cursor)

    async def recover_stale_submitting(self) -> int:
        rows = await (await self._db.execute("SELECT * FROM generation_jobs WHERE status = 'submitting'")).fetchall()
        count = 0
        for row in rows:
            stored = await self.get(JobId(row["job_id"]))
            if stored is None:
                continue
            now = datetime.now(UTC)
            error = DomainError(
                code=ErrorCode.SUBMISSION_OUTCOME_UNKNOWN,
                stage=ErrorStage.SUBMIT,
                category=ErrorCategory.STATE_CONFLICT,
                retryable=False,
                safe_message="The process stopped before a reliable ModelScope task identifier was recorded.",
                occurred_at=now,
                possibly_submitted=True,
            )
            await self.save(stored.job.mark_submission_failed(error=error, now=now), expected_revision=stored.revision)
            count += 1
        return count

    async def schedule_expired_terminal(self, *, cutoff: datetime, limit: int = 100) -> int:
        rows = tuple(
            await (
                await self._db.execute(
                    "SELECT job_id FROM generation_jobs "
                    "WHERE status IN ('succeeded','failed') AND updated_at < ? "
                    "ORDER BY updated_at LIMIT ?",
                    (cutoff.isoformat(), limit),
                )
            ).fetchall()
        )
        if not rows:
            return 0
        now = datetime.now(UTC).isoformat()
        try:
            await self._db.execute("BEGIN IMMEDIATE")
            for row in rows:
                job_id = row["job_id"]
                await self._db.execute(
                    "INSERT INTO artifact_cleanup_queue"
                    "(cleanup_id, job_id, relative_job_dir, attempts, created_at, updated_at) "
                    "VALUES(?,?,?,?,?,?)",
                    (str(uuid7()), job_id, f"jobs/{job_id}", 0, now, now),
                )
                await self._db.execute("DELETE FROM generation_jobs WHERE job_id = ?", (job_id,))
            await self._db.commit()
        except Exception:
            await self._db.rollback()
            raise
        return len(rows)

    async def cleanup_items(self, *, limit: int = 100) -> tuple[dict[str, Any], ...]:
        rows = tuple(
            await (
                await self._db.execute(
                    "SELECT cleanup_id, job_id, relative_job_dir, attempts "
                    "FROM artifact_cleanup_queue ORDER BY created_at LIMIT ?",
                    (limit,),
                )
            ).fetchall()
        )
        return tuple(dict(row) for row in rows)

    async def complete_cleanup(self, cleanup_id: str) -> None:
        await self._db.execute("DELETE FROM artifact_cleanup_queue WHERE cleanup_id = ?", (cleanup_id,))
        await self._db.commit()

    async def fail_cleanup(self, cleanup_id: str, message: str) -> None:
        await self._db.execute(
            "UPDATE artifact_cleanup_queue SET attempts = attempts + 1, "
            "last_error_message = ?, updated_at = ? WHERE cleanup_id = ?",
            (message[:500], datetime.now(UTC).isoformat(), cleanup_id),
        )
        await self._db.commit()

    async def _replace_images(self, job: GenerationJob) -> None:
        await self._db.execute("DELETE FROM generated_images WHERE job_id = ?", (str(job.job_id),))
        for image in job.images:
            values = _image_values(job, image)
            await self._db.execute(
                f"INSERT INTO generated_images ({', '.join(values)}) VALUES ({', '.join('?' for _ in values)})",
                tuple(values.values()),
            )

    async def _load_images(self, job_id: str) -> tuple[aiosqlite.Row, ...]:
        rows = await (
            await self._db.execute("SELECT * FROM generated_images WHERE job_id = ? ORDER BY position", (job_id,))
        ).fetchall()
        return tuple(rows)


def _error_values(error: DomainError | None, *, prefix: str = "error_") -> dict[str, Any]:
    return {
        prefix + "code": error.code.value if error else None,
        prefix + "stage": error.stage.value if error else None,
        prefix + "category": error.category.value if error else None,
        prefix + "retryable": int(error.retryable) if error else None,
        prefix + "retry_after_seconds": error.retry_after_seconds if error else None,
        prefix + "safe_message": error.safe_message if error else None,
        prefix + "provider_request_id": error.provider_request_id if error else None,
        prefix + "occurred_at": error.occurred_at.isoformat() if error else None,
    }


def _job_values(job: GenerationJob, *, revision: int) -> dict[str, Any]:
    task = job.provider_task
    values: dict[str, Any] = {
        "job_id": str(job.job_id),
        "revision": revision,
        "status": job.status.value,
        "prompt": job.request.prompt,
        "model": job.request.model,
        "size_width": job.request.size.width,
        "size_height": job.request.size.height,
        "negative_prompt": job.request.negative_prompt,
        "seed": job.request.seed,
        "provider": "modelscope" if task else None,
        "provider_task_id": task.task_id if task else None,
        "provider_request_id": task.provider_request_id if task else None,
        "last_provider_status": task.last_provider_status if task else None,
    }
    values.update(_error_values(job.last_error))
    values["error_possibly_submitted"] = int(job.last_error.possibly_submitted) if job.last_error else None
    values.update(
        {
            "created_at": job.created_at.isoformat(),
            "updated_at": job.updated_at.isoformat(),
            "submitted_at": job.submitted_at.isoformat() if job.submitted_at else None,
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        }
    )
    return values


def _image_values(job: GenerationJob, image: GeneratedImage) -> dict[str, Any]:
    artifact = image.local_artifact
    values: dict[str, Any] = {
        "image_id": str(image.image_id),
        "job_id": str(job.job_id),
        "position": image.position,
        "provider_locator": image.provider_reference.locator,
        "provider_metadata_json": json.dumps(
            {"version": 1, "provider_request_id": image.provider_reference.provider_request_id}
        ),
        "artifact_status": image.artifact_status.value,
        "artifact_key": str(artifact.artifact_key) if artifact else None,
        "relative_path": artifact.relative_path if artifact else None,
        "sha256": artifact.sha256 if artifact else None,
        "byte_size": artifact.byte_size if artifact else None,
        "media_type": artifact.media_type if artifact else None,
        "image_format": artifact.format if artifact else None,
        "width": artifact.width if artifact else None,
        "height": artifact.height if artifact else None,
        "saved_at": artifact.saved_at.isoformat() if artifact else None,
    }
    values.update(_error_values(image.last_error))
    values.update({"created_at": job.created_at.isoformat(), "updated_at": job.updated_at.isoformat()})
    return values


def _row_error(row: aiosqlite.Row, *, possibly: bool = False) -> DomainError | None:
    if row["error_code"] is None:
        return None
    return DomainError(
        code=ErrorCode(row["error_code"]),
        stage=ErrorStage(row["error_stage"]),
        category=ErrorCategory(row["error_category"]),
        retryable=bool(row["error_retryable"]),
        retry_after_seconds=row["error_retry_after_seconds"],
        safe_message=row["error_safe_message"],
        provider_request_id=row["error_provider_request_id"],
        possibly_submitted=bool(row["error_possibly_submitted"]) if possibly else False,
        occurred_at=datetime.fromisoformat(row["error_occurred_at"]),
    )


def _row_to_job(row: aiosqlite.Row, image_rows: tuple[aiosqlite.Row, ...], artifact_root: Path) -> GenerationJob:
    task = None
    if row["provider_task_id"]:
        task = ProviderTaskReference(row["provider_task_id"], row["provider_request_id"], row["last_provider_status"])
    images: list[GeneratedImage] = []
    for image_row in image_rows:
        metadata = json.loads(image_row["provider_metadata_json"] or "{}")
        artifact = None
        if image_row["artifact_status"] == ArtifactStatus.AVAILABLE.value:
            relative = image_row["relative_path"]
            artifact = LocalArtifact(
                artifact_key=ArtifactKey(image_row["artifact_key"]),
                file_path=str((artifact_root / relative).resolve()),
                relative_path=relative,
                sha256=image_row["sha256"],
                byte_size=image_row["byte_size"],
                media_type=image_row["media_type"],
                format=image_row["image_format"],
                width=image_row["width"],
                height=image_row["height"],
                saved_at=datetime.fromisoformat(image_row["saved_at"]),
            )
        images.append(
            GeneratedImage(
                image_id=ImageId(image_row["image_id"]),
                position=image_row["position"],
                provider_reference=ProviderImageReference(
                    image_row["provider_locator"], metadata.get("provider_request_id")
                ),
                artifact_status=ArtifactStatus(image_row["artifact_status"]),
                local_artifact=artifact,
                last_error=_row_error(image_row),
            )
        )
    return GenerationJob(
        job_id=JobId(row["job_id"]),
        request=GenerationRequest(
            prompt=row["prompt"],
            model=row["model"],
            size=ImageSize(row["size_width"], row["size_height"]),
            negative_prompt=row["negative_prompt"],
            seed=row["seed"],
        ),
        status=JobStatus(row["status"]),
        provider_task=task,
        images=tuple(images),
        last_error=_row_error(row, possibly=True),
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
        submitted_at=datetime.fromisoformat(row["submitted_at"]) if row["submitted_at"] else None,
        completed_at=datetime.fromisoformat(row["completed_at"]) if row["completed_at"] else None,
    )


def _encode_cursor(updated_at: str, job_id: str, fingerprint: str) -> str:
    payload = json.dumps({"v": 1, "u": updated_at, "j": job_id, "f": fingerprint}, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(payload).decode().rstrip("=")


def _decode_cursor(value: str, fingerprint: str) -> tuple[str, str]:
    try:
        padded = value + "=" * (-len(value) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded).decode())
        if payload.get("v") != 1 or payload.get("f") != fingerprint:
            raise ValueError
        return str(payload["u"]), str(payload["j"])
    except Exception as exc:
        raise ValueError("INVALID_CURSOR") from exc
