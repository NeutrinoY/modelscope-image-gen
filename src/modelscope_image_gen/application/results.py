from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from modelscope_image_gen.domain import DomainError, GenerationJob, JobId

from .views import GeneratedImageView, JobSummaryView


class NextStepKind(StrEnum):
    CHECK = "check"
    FETCH = "fetch"


@dataclass(frozen=True, slots=True)
class NextStep:
    kind: NextStepKind
    job_id: JobId
    recommended_wait_seconds: int | None = None


@dataclass(frozen=True, slots=True)
class SubmitResult:
    ok: bool
    job: GenerationJob | None
    accepted: bool
    error: DomainError | None = None


@dataclass(frozen=True, slots=True)
class CheckResult:
    ok: bool
    job: GenerationJob
    error: DomainError | None = None


@dataclass(frozen=True, slots=True)
class FetchResult:
    ok: bool
    job: GenerationJob
    images: tuple[GeneratedImageView, ...]
    partial: bool
    error: DomainError | None = None


@dataclass(frozen=True, slots=True)
class GenerateResult:
    ok: bool
    job: GenerationJob | None
    images: tuple[GeneratedImageView, ...]
    completed: bool
    partial: bool
    error: DomainError | None = None


@dataclass(frozen=True, slots=True)
class ListResult:
    ok: bool
    items: tuple[JobSummaryView, ...]
    next_cursor: str | None
    error: DomainError | None = None
