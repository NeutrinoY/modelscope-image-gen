from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from modelscope_image_gen.domain import DomainError, GeneratedImage, GenerationJob


class NextTool(StrEnum):
    CHECK = "check_image_generation"
    FETCH = "fetch_image_generation_result"


@dataclass(frozen=True, slots=True)
class NextStep:
    tool: NextTool
    job_id: str
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
    images: tuple[GeneratedImage, ...]
    partial: bool
    error: DomainError | None = None


@dataclass(frozen=True, slots=True)
class GenerateResult:
    ok: bool
    job: GenerationJob | None
    images: tuple[GeneratedImage, ...]
    completed: bool
    partial: bool
    error: DomainError | None = None


@dataclass(frozen=True, slots=True)
class JobPage:
    items: tuple[GenerationJob, ...]
    next_cursor: str | None


@dataclass(frozen=True, slots=True)
class ListResult:
    ok: bool
    items: tuple[GenerationJob, ...]
    next_cursor: str | None
    error: DomainError | None = None
