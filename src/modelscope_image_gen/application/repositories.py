from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from modelscope_image_gen.domain import DomainError, GenerationJob, JobId, JobStatus

from .views import JobSummaryView


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
    items: tuple[JobSummaryView, ...]
    next_cursor: str | None


class RepositoryError(Exception):
    def __init__(self, error: DomainError) -> None:
        super().__init__(error.safe_message)
        self.error = error


class GenerationJobRepository(Protocol):
    async def add(self, job: GenerationJob) -> StoredGenerationJob: ...
    async def get(self, job_id: JobId) -> StoredGenerationJob | None: ...
    async def save(self, job: GenerationJob, *, expected_revision: int) -> StoredGenerationJob: ...
    async def list(self, query: JobListQuery) -> StoredJobPage: ...
    async def recover_stale_submitting(self) -> int: ...
