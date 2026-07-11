from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from modelscope_image_gen.domain import (
    ArtifactAggregateStatus,
    ArtifactStatus,
    DomainError,
    ImageId,
    ImageSize,
    JobId,
    JobStatus,
)


@dataclass(frozen=True, slots=True)
class GeneratedImageView:
    image_id: ImageId
    position: int
    artifact_status: ArtifactStatus
    file_path: str | None
    relative_path: str | None
    sha256: str | None
    byte_size: int | None
    media_type: str | None
    format: str | None
    width: int | None
    height: int | None
    saved_at: datetime | None
    last_error: DomainError | None


@dataclass(frozen=True, slots=True)
class JobSummaryView:
    job_id: JobId
    status: JobStatus
    artifact_status: ArtifactAggregateStatus
    model: str
    size: ImageSize
    image_count: int
    available_image_count: int
    created_at: datetime
    updated_at: datetime
    last_error_summary: str | None
