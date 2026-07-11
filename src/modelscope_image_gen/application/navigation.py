from __future__ import annotations

from modelscope_image_gen.domain import GenerationJob, JobId, JobStatus

from .results import NextStep, NextStepKind
from .views import JobSummaryView


def next_step_for_job(job: GenerationJob, *, wait_seconds: int) -> NextStep | None:
    return _derive_next_step(
        job_id=job.job_id,
        status=job.status,
        image_count=len(job.images),
        available_image_count=job.available_image_count,
        wait_seconds=wait_seconds,
    )


def next_step_for_summary(summary: JobSummaryView, *, wait_seconds: int) -> NextStep | None:
    return _derive_next_step(
        job_id=summary.job_id,
        status=summary.status,
        image_count=summary.image_count,
        available_image_count=summary.available_image_count,
        wait_seconds=wait_seconds,
    )


def _derive_next_step(
    *, job_id: JobId, status: JobStatus, image_count: int, available_image_count: int, wait_seconds: int
) -> NextStep | None:
    if status in {JobStatus.SUBMITTED, JobStatus.IN_PROGRESS}:
        return NextStep(NextStepKind.CHECK, job_id, max(1, wait_seconds))
    if status is JobStatus.SUCCEEDED and available_image_count < image_count:
        return NextStep(NextStepKind.FETCH, job_id)
    return None
