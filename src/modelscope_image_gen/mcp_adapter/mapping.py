from __future__ import annotations

from modelscope_image_gen.application.navigation import next_step_for_job, next_step_for_summary
from modelscope_image_gen.application.results import NextStep, NextStepKind
from modelscope_image_gen.application.views import GeneratedImageView, JobSummaryView
from modelscope_image_gen.domain import DomainError, GenerationJob, JobStatus
from modelscope_image_gen.mcp_adapter.models.outputs import (
    ErrorOutput,
    GeneratedImageOutput,
    ImageSizeOutput,
    JobOutput,
    JobSummaryOutput,
    NextActionOutput,
)


def next_action(job: GenerationJob, *, wait_seconds: int) -> NextActionOutput | None:
    return _next_action_output(next_step_for_job(job, wait_seconds=wait_seconds))


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


def image_output(image: GeneratedImageView) -> GeneratedImageOutput:
    return GeneratedImageOutput(
        image_id=str(image.image_id),
        position=image.position,
        artifact_status=image.artifact_status,
        file_path=image.file_path,
        relative_path=image.relative_path,
        sha256=image.sha256,
        byte_size=image.byte_size,
        media_type=image.media_type,
        format=image.format,
        width=image.width,
        height=image.height,
        saved_at=image.saved_at.isoformat() if image.saved_at else None,
        last_error=error_output(image.last_error),
    )


def job_summary(job: JobSummaryView, *, wait_seconds: int) -> JobSummaryOutput:
    action = _next_action_output(next_step_for_summary(job, wait_seconds=wait_seconds))
    return JobSummaryOutput(
        job_id=str(job.job_id),
        status=job.status,
        artifact_status=job.artifact_status,
        model=job.model,
        size=ImageSizeOutput(width=job.size.width, height=job.size.height),
        image_count=job.image_count,
        available_image_count=job.available_image_count,
        created_at=job.created_at.isoformat(),
        updated_at=job.updated_at.isoformat(),
        last_error_summary=job.last_error_summary,
        next_action=action,
    )


def _next_action_output(step: NextStep | None) -> NextActionOutput | None:
    if step is None:
        return None
    tool = "check_image_generation" if step.kind is NextStepKind.CHECK else "fetch_image_generation_result"
    return NextActionOutput(
        tool=tool,
        job_id=str(step.job_id),
        recommended_wait_seconds=step.recommended_wait_seconds,
    )
