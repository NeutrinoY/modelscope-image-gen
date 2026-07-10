from __future__ import annotations

from modelscope_image_gen.domain import DomainError, GeneratedImage, GenerationJob, JobStatus
from modelscope_image_gen.mcp_adapter.models.outputs import (
    ErrorOutput,
    GeneratedImageOutput,
    ImageSizeOutput,
    JobOutput,
    JobSummaryOutput,
    NextActionOutput,
)


def next_action(job: GenerationJob, *, wait_seconds: int) -> NextActionOutput | None:
    if job.status in {JobStatus.SUBMITTED, JobStatus.IN_PROGRESS}:
        return NextActionOutput(
            tool="check_image_generation", job_id=str(job.job_id), recommended_wait_seconds=max(1, wait_seconds)
        )
    if job.status is JobStatus.SUCCEEDED and job.available_image_count < len(job.images):
        return NextActionOutput(
            tool="fetch_image_generation_result", job_id=str(job.job_id), recommended_wait_seconds=None
        )
    return None


def error_output(error: DomainError | None, *, action: NextActionOutput | None = None) -> ErrorOutput | None:
    if error is None:
        return None
    return ErrorOutput(
        code=error.code.value,
        stage=error.stage,
        category=error.category,
        retryable=error.retryable,
        retry_after_seconds=error.retry_after_seconds,
        message=error.safe_message,
        possibly_submitted=error.possibly_submitted,
        provider_request_id=error.provider_request_id,
        next_action=action,
    )


def job_output(job: GenerationJob, *, wait_seconds: int) -> JobOutput:
    action = next_action(job, wait_seconds=wait_seconds)
    return JobOutput(
        job_id=str(job.job_id),
        status=job.status,
        artifact_status=job.artifact_status,
        is_terminal=job.status.is_terminal,
        result_ready=job.status is JobStatus.SUCCEEDED,
        model=job.request.model,
        size=ImageSizeOutput(width=job.request.size.width, height=job.request.size.height),
        seed=job.request.seed,
        image_count=len(job.images),
        available_image_count=job.available_image_count,
        created_at=job.created_at.isoformat(),
        updated_at=job.updated_at.isoformat(),
        submitted_at=job.submitted_at.isoformat() if job.submitted_at else None,
        completed_at=job.completed_at.isoformat() if job.completed_at else None,
        last_error=error_output(job.last_error, action=action if job.last_error and job.last_error.retryable else None),
        next_action=action,
    )


def image_output(image: GeneratedImage) -> GeneratedImageOutput:
    artifact = image.local_artifact
    return GeneratedImageOutput(
        image_id=str(image.image_id),
        position=image.position,
        artifact_status=image.artifact_status,
        file_path=artifact.file_path if artifact else None,
        relative_path=artifact.relative_path if artifact else None,
        sha256=artifact.sha256 if artifact else None,
        byte_size=artifact.byte_size if artifact else None,
        media_type=artifact.media_type if artifact else None,
        format=artifact.format if artifact else None,
        width=artifact.width if artifact else None,
        height=artifact.height if artifact else None,
        saved_at=artifact.saved_at.isoformat() if artifact else None,
        last_error=error_output(image.last_error),
    )


def job_summary(job: GenerationJob, *, wait_seconds: int) -> JobSummaryOutput:
    summary = f"[{job.last_error.code.value}] {job.last_error.safe_message}" if job.last_error else None
    return JobSummaryOutput(
        job_id=str(job.job_id),
        status=job.status,
        artifact_status=job.artifact_status,
        model=job.request.model,
        size=ImageSizeOutput(width=job.request.size.width, height=job.request.size.height),
        image_count=len(job.images),
        available_image_count=job.available_image_count,
        created_at=job.created_at.isoformat(),
        updated_at=job.updated_at.isoformat(),
        last_error_summary=summary,
        next_action=next_action(job, wait_seconds=wait_seconds),
    )
