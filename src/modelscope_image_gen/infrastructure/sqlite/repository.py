from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid7

import aiosqlite
import anyio

from modelscope_image_gen.application.repositories import (
    JobListQuery,
    RepositoryError,
    StoredGenerationJob,
    StoredJobPage,
)
from modelscope_image_gen.domain import (
    DomainError,
    ErrorCategory,
    ErrorCode,
    ErrorStage,
    GenerationJob,
    JobId,
)

from .pagination import decode_cursor, encode_cursor, filter_fingerprint
from .row_mapping import image_values, job_values, row_to_job, row_to_summary

SCHEMA_VERSION = 1
logger = logging.getLogger("modelscope-image-gen-mcp")


class SqliteGenerationJobRepository:
    def __init__(self, connection: aiosqlite.Connection) -> None:
        self._db = connection

    @classmethod
    async def open(cls, database_path: Path) -> SqliteGenerationJobRepository:
        database_path.parent.mkdir(parents=True, exist_ok=True)
        db = await aiosqlite.connect(database_path)
        try:
            db.row_factory = aiosqlite.Row
            await db.execute("PRAGMA foreign_keys = ON")
            await db.execute("PRAGMA journal_mode = WAL")
            await db.execute("PRAGMA synchronous = NORMAL")
            await db.execute("PRAGMA busy_timeout = 5000")
            row = await (await db.execute("PRAGMA user_version")).fetchone()
            if row is None:
                raise RuntimeError("could not read SQLite schema version")
            version = int(row[0])
            if version > SCHEMA_VERSION:
                raise RuntimeError(
                    f"database schema version {version} is newer than supported version {SCHEMA_VERSION}"
                )
            if version == 0:
                script = (Path(__file__).parent / "migrations" / "v001_initial.sql").read_text(encoding="utf-8")
                await db.executescript(script)
                await db.commit()
                logger.info("database.migrated from_version=0 to_version=%d", SCHEMA_VERSION)
        except BaseException:
            with anyio.CancelScope(shield=True):
                await db.close()
            raise
        return cls(db)

    async def close(self) -> None:
        await self._db.close()

    async def add(self, job: GenerationJob) -> StoredGenerationJob:
        values = job_values(job, revision=0)
        columns = ", ".join(values)
        placeholders = ", ".join("?" for _ in values)
        with _translate_persistence_errors():
            async with self._write_transaction():
                await self._db.execute(
                    f"INSERT INTO generation_jobs ({columns}) VALUES ({placeholders})", tuple(values.values())
                )
                await self._replace_images(job)
        return StoredGenerationJob(job, 0)

    async def get(self, job_id: JobId) -> StoredGenerationJob | None:
        with _translate_persistence_errors():
            row = await (
                await self._db.execute("SELECT * FROM generation_jobs WHERE job_id = ?", (str(job_id),))
            ).fetchone()
            if row is None:
                return None
            images = await self._load_images(str(job_id))
            return StoredGenerationJob(row_to_job(row, images), int(row["revision"]))

    async def save(self, job: GenerationJob, *, expected_revision: int) -> StoredGenerationJob:
        next_revision = expected_revision + 1
        values = job_values(job, revision=next_revision)
        assignments = ", ".join(f"{name} = ?" for name in values if name != "job_id")
        params = (
            *(value for name, value in values.items() if name != "job_id"),
            str(job.job_id),
            expected_revision,
        )
        with _translate_persistence_errors():
            async with self._write_transaction():
                cursor = await self._db.execute(
                    f"UPDATE generation_jobs SET {assignments} WHERE job_id = ? AND revision = ?",
                    params,
                )
                if cursor.rowcount != 1:
                    raise RepositoryError(
                        _persistence_error(
                            ErrorCode.CONCURRENT_MODIFICATION,
                            "The image generation job changed during this operation; retry with the latest state.",
                        )
                    )
                await self._replace_images(job)
        return StoredGenerationJob(job, next_revision)

    async def list(self, query: JobListQuery) -> StoredJobPage:
        statuses = tuple(sorted({status.value for status in query.statuses})) if query.statuses else ()
        fingerprint = filter_fingerprint(statuses)
        cursor_values: tuple[str, str] | None = None
        if query.cursor:
            cursor_values = decode_cursor(query.cursor, fingerprint)
        where: list[str] = []
        params: list[Any] = []
        if statuses:
            where.append(f"g.status IN ({','.join('?' for _ in statuses)})")
            params.extend(statuses)
        if cursor_values:
            where.append("(g.updated_at < ? OR (g.updated_at = ? AND g.job_id < ?))")
            params.extend((cursor_values[0], cursor_values[0], cursor_values[1]))
        sql = (
            "SELECT g.job_id, g.status, g.model, g.size_width, g.size_height, "
            "g.created_at, g.updated_at, g.error_code, g.error_safe_message, "
            "COUNT(i.image_id) AS image_count, "
            "COALESCE(SUM(CASE WHEN i.artifact_status = 'available' THEN 1 ELSE 0 END), 0) AS available_count, "
            "COALESCE(SUM(CASE WHEN i.artifact_status = 'failed' THEN 1 ELSE 0 END), 0) AS failed_count "
            "FROM generation_jobs AS g LEFT JOIN generated_images AS i ON i.job_id = g.job_id"
        )
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " GROUP BY g.job_id ORDER BY g.updated_at DESC, g.job_id DESC LIMIT ?"
        params.append(query.limit + 1)
        with _translate_persistence_errors():
            rows = tuple(await (await self._db.execute(sql, tuple(params))).fetchall())
        has_more = len(rows) > query.limit
        rows = rows[: query.limit]
        items = tuple(row_to_summary(row) for row in rows)
        next_cursor = None
        if has_more and rows:
            last = rows[-1]
            next_cursor = encode_cursor(last["updated_at"], last["job_id"], fingerprint)
        return StoredJobPage(items, next_cursor)

    async def recover_stale_submitting(self) -> int:
        with _translate_persistence_errors():
            rows = await (
                await self._db.execute("SELECT * FROM generation_jobs WHERE status = 'submitting'")
            ).fetchall()
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
        with _translate_persistence_errors():
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
        with _translate_persistence_errors():
            async with self._write_transaction():
                for row in rows:
                    job_id = row["job_id"]
                    await self._db.execute(
                        "INSERT INTO artifact_cleanup_queue"
                        "(cleanup_id, job_id, relative_job_dir, attempts, created_at, updated_at) "
                        "VALUES(?,?,?,?,?,?)",
                        (str(uuid7()), job_id, f"jobs/{job_id}", 0, now, now),
                    )
                    await self._db.execute("DELETE FROM generation_jobs WHERE job_id = ?", (job_id,))
        return len(rows)

    async def cleanup_items(self, *, limit: int = 100) -> tuple[dict[str, Any], ...]:
        with _translate_persistence_errors():
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
        with _translate_persistence_errors():
            async with self._write_transaction():
                await self._db.execute("DELETE FROM artifact_cleanup_queue WHERE cleanup_id = ?", (cleanup_id,))

    async def fail_cleanup(self, cleanup_id: str, message: str) -> None:
        with _translate_persistence_errors():
            async with self._write_transaction():
                await self._db.execute(
                    "UPDATE artifact_cleanup_queue SET attempts = attempts + 1, "
                    "last_error_message = ?, updated_at = ? WHERE cleanup_id = ?",
                    (message[:500], datetime.now(UTC).isoformat(), cleanup_id),
                )

    @asynccontextmanager
    async def _write_transaction(self) -> AsyncIterator[None]:
        try:
            await self._db.execute("BEGIN IMMEDIATE")
            yield
            await self._db.commit()
        except BaseException:
            with anyio.CancelScope(shield=True):
                try:
                    await self._db.rollback()
                except aiosqlite.Error:
                    pass
            raise

    async def _replace_images(self, job: GenerationJob) -> None:
        await self._db.execute("DELETE FROM generated_images WHERE job_id = ?", (str(job.job_id),))
        for image in job.images:
            values = image_values(job, image)
            await self._db.execute(
                f"INSERT INTO generated_images ({', '.join(values)}) VALUES ({', '.join('?' for _ in values)})",
                tuple(values.values()),
            )

    async def _load_images(self, job_id: str) -> tuple[aiosqlite.Row, ...]:
        rows = await (
            await self._db.execute("SELECT * FROM generated_images WHERE job_id = ? ORDER BY position", (job_id,))
        ).fetchall()
        return tuple(rows)


def _persistence_error(code: ErrorCode, message: str) -> DomainError:
    return DomainError(
        code=code,
        stage=ErrorStage.PERSISTENCE,
        category=ErrorCategory.STATE_CONFLICT if code is ErrorCode.CONCURRENT_MODIFICATION else ErrorCategory.LOCAL_IO,
        retryable=True,
        retry_after_seconds=1,
        safe_message=message,
        occurred_at=datetime.now(UTC),
    )


@contextmanager
def _translate_persistence_errors() -> Iterator[None]:
    try:
        yield
    except aiosqlite.Error as exc:
        raise RepositoryError(
            _persistence_error(
                ErrorCode.PERSISTENCE_ERROR,
                "The local image generation state could not be read or saved.",
            )
        ) from exc
