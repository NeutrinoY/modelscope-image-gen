from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from modelscope_image_gen.domain import ArtifactAggregateStatus, ArtifactStatus, ErrorCategory, ErrorStage, JobStatus


class WireModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ImageSizeOutput(WireModel):
    width: int
    height: int


class NextActionOutput(WireModel):
    tool: Literal["check_image_generation", "fetch_image_generation_result"]
    job_id: str
    recommended_wait_seconds: int | None = None


class ErrorOutput(WireModel):
    code: str
    stage: ErrorStage
    category: ErrorCategory
    retryable: bool
    retry_after_seconds: int | None
    message: str
    possibly_submitted: bool
    provider_request_id: str | None
    next_action: NextActionOutput | None


class JobOutput(WireModel):
    job_id: str
    status: JobStatus
    artifact_status: ArtifactAggregateStatus
    is_terminal: bool
    result_ready: bool
    model: str
    size: ImageSizeOutput
    seed: int | None
    image_count: int
    available_image_count: int
    created_at: str
    updated_at: str
    submitted_at: str | None
    completed_at: str | None
    last_error: ErrorOutput | None
    next_action: NextActionOutput | None


class GeneratedImageOutput(WireModel):
    image_id: str
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
    saved_at: str | None
    last_error: ErrorOutput | None


class JobSummaryOutput(WireModel):
    job_id: str
    status: JobStatus
    artifact_status: ArtifactAggregateStatus
    model: str
    size: ImageSizeOutput
    image_count: int
    available_image_count: int
    created_at: str
    updated_at: str
    last_error_summary: str | None
    next_action: NextActionOutput | None


class SubmitData(WireModel):
    job: JobOutput
    accepted: bool


class CheckData(WireModel):
    job: JobOutput


class FetchData(WireModel):
    job: JobOutput
    images: list[GeneratedImageOutput]
    partial: bool


class ListData(WireModel):
    items: list[JobSummaryOutput]
    next_cursor: str | None


class GenerateData(WireModel):
    job: JobOutput
    images: list[GeneratedImageOutput]
    completed: bool
    partial: bool


class SubmitToolOutput(WireModel):
    ok: bool
    data: SubmitData | None
    error: ErrorOutput | None


class CheckToolOutput(WireModel):
    ok: bool
    data: CheckData | None
    error: ErrorOutput | None


class FetchToolOutput(WireModel):
    ok: bool
    data: FetchData | None
    error: ErrorOutput | None


class ListToolOutput(WireModel):
    ok: bool
    data: ListData | None
    error: ErrorOutput | None


class GenerateToolOutput(WireModel):
    ok: bool
    data: GenerateData | None
    error: ErrorOutput | None
