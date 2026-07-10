from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from modelscope_image_gen.domain import GenerationJob, JobId, JobStatus


@dataclass(frozen=True, slots=True)
class StoredGenerationJob:
    job: GenerationJob
    revision: int


@dataclass(frozen=True, slots=True)
class JobListQuery:
    statuses: tuple[JobStatus, ...] | None = None
    limit: int = 20
    cursor: str | None = None


@dataclass(frozen=True, slots=True)
class StoredJobPage:
    items: tuple[StoredGenerationJob, ...]
    next_cursor: str | None


class GenerationJobRepository(Protocol):
    async def add(self, job: GenerationJob) -> StoredGenerationJob: ...
    async def get(self, job_id: JobId) -> StoredGenerationJob | None: ...
    async def save(self, job: GenerationJob, *, expected_revision: int) -> StoredGenerationJob: ...
    async def list(self, query: JobListQuery) -> StoredJobPage: ...
    async def recover_stale_submitting(self) -> int: ...
