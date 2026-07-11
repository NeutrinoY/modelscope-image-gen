from __future__ import annotations

import json
from datetime import datetime
from typing import Any

import aiosqlite

from modelscope_image_gen.application.views import JobSummaryView
from modelscope_image_gen.domain import (
    ArtifactAggregateStatus,
    ArtifactKey,
    ArtifactStatus,
    DomainError,
    ErrorCategory,
    ErrorCode,
    ErrorStage,
    GeneratedImage,
    GenerationJob,
    GenerationRequest,
    ImageId,
    ImageSize,
    JobId,
    JobStatus,
    LocalArtifact,
    ProviderImageReference,
    ProviderName,
    ProviderTaskReference,
)


def job_values(job: GenerationJob, *, revision: int) -> dict[str, Any]:
    task = job.provider_task
    values: dict[str, Any] = {
        "job_id": str(job.job_id),
        "revision": revision,
        "status": job.status.value,
        "prompt": job.request.prompt,
        "model": job.request.model,
        "size_width": job.request.size.width,
        "size_height": job.request.size.height,
        "negative_prompt": job.request.negative_prompt,
        "seed": job.request.seed,
        "provider": task.provider.value if task else None,
        "provider_task_id": task.task_id if task else None,
        "provider_request_id": task.provider_request_id if task else None,
        "last_provider_status": task.last_provider_status if task else None,
    }
    values.update(_error_values(job.last_error))
    values["error_possibly_submitted"] = int(job.last_error.possibly_submitted) if job.last_error else None
    values.update(
        {
            "created_at": job.created_at.isoformat(),
            "updated_at": job.updated_at.isoformat(),
            "submitted_at": job.submitted_at.isoformat() if job.submitted_at else None,
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        }
    )
    return values


def image_values(job: GenerationJob, image: GeneratedImage) -> dict[str, Any]:
    artifact = image.local_artifact
    values: dict[str, Any] = {
        "image_id": str(image.image_id),
        "job_id": str(job.job_id),
        "position": image.position,
        "provider_locator": image.provider_reference.locator,
        "provider_metadata_json": json.dumps(
            {"version": 1, "provider_request_id": image.provider_reference.provider_request_id}
        ),
        "artifact_status": image.artifact_status.value,
        "artifact_key": str(artifact.artifact_key) if artifact else None,
        "relative_path": artifact.relative_path if artifact else None,
        "sha256": artifact.sha256 if artifact else None,
        "byte_size": artifact.byte_size if artifact else None,
        "media_type": artifact.media_type if artifact else None,
        "image_format": artifact.format if artifact else None,
        "width": artifact.width if artifact else None,
        "height": artifact.height if artifact else None,
        "saved_at": artifact.saved_at.isoformat() if artifact else None,
    }
    values.update(_error_values(image.last_error))
    values.update({"created_at": job.created_at.isoformat(), "updated_at": job.updated_at.isoformat()})
    return values


def row_to_job(row: aiosqlite.Row, image_rows: tuple[aiosqlite.Row, ...]) -> GenerationJob:
    task = None
    if row["provider_task_id"]:
        task = ProviderTaskReference(
            task_id=row["provider_task_id"],
            provider_request_id=row["provider_request_id"],
            last_provider_status=row["last_provider_status"],
            provider=ProviderName(row["provider"]),
        )
    images: list[GeneratedImage] = []
    for image_row in image_rows:
        metadata = json.loads(image_row["provider_metadata_json"] or "{}")
        artifact = None
        if image_row["artifact_status"] == ArtifactStatus.AVAILABLE.value:
            artifact = LocalArtifact(
                artifact_key=ArtifactKey(image_row["artifact_key"]),
                relative_path=image_row["relative_path"],
                sha256=image_row["sha256"],
                byte_size=image_row["byte_size"],
                media_type=image_row["media_type"],
                format=image_row["image_format"],
                width=image_row["width"],
                height=image_row["height"],
                saved_at=datetime.fromisoformat(image_row["saved_at"]),
            )
        images.append(
            GeneratedImage(
                image_id=ImageId(image_row["image_id"]),
                position=image_row["position"],
                provider_reference=ProviderImageReference(
                    image_row["provider_locator"], metadata.get("provider_request_id")
                ),
                artifact_status=ArtifactStatus(image_row["artifact_status"]),
                local_artifact=artifact,
                last_error=_row_error(image_row),
            )
        )
    return GenerationJob(
        job_id=JobId(row["job_id"]),
        request=GenerationRequest(
            prompt=row["prompt"],
            model=row["model"],
            size=ImageSize(row["size_width"], row["size_height"]),
            negative_prompt=row["negative_prompt"],
            seed=row["seed"],
        ),
        status=JobStatus(row["status"]),
        provider_task=task,
        images=tuple(images),
        last_error=_row_error(row, possibly=True),
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
        submitted_at=datetime.fromisoformat(row["submitted_at"]) if row["submitted_at"] else None,
        completed_at=datetime.fromisoformat(row["completed_at"]) if row["completed_at"] else None,
    )


def row_to_summary(row: aiosqlite.Row) -> JobSummaryView:
    status = JobStatus(row["status"])
    image_count = int(row["image_count"])
    available_count = int(row["available_count"])
    failed_count = int(row["failed_count"])
    if status is not JobStatus.SUCCEEDED:
        artifact_status = ArtifactAggregateStatus.NOT_READY
    elif available_count == image_count:
        artifact_status = ArtifactAggregateStatus.AVAILABLE
    elif available_count:
        artifact_status = ArtifactAggregateStatus.PARTIAL
    elif failed_count == image_count:
        artifact_status = ArtifactAggregateStatus.FAILED
    else:
        artifact_status = ArtifactAggregateStatus.PENDING
    error_summary = None
    if row["error_code"]:
        error_summary = f"[{row['error_code']}] {row['error_safe_message']}"
    return JobSummaryView(
        job_id=JobId(row["job_id"]),
        status=status,
        artifact_status=artifact_status,
        model=row["model"],
        size=ImageSize(row["size_width"], row["size_height"]),
        image_count=image_count,
        available_image_count=available_count,
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
        last_error_summary=error_summary,
    )


def _error_values(error: DomainError | None, *, prefix: str = "error_") -> dict[str, Any]:
    return {
        prefix + "code": error.code.value if error else None,
        prefix + "stage": error.stage.value if error else None,
        prefix + "category": error.category.value if error else None,
        prefix + "retryable": int(error.retryable) if error else None,
        prefix + "retry_after_seconds": error.retry_after_seconds if error else None,
        prefix + "safe_message": error.safe_message if error else None,
        prefix + "provider_request_id": error.provider_request_id if error else None,
        prefix + "occurred_at": error.occurred_at.isoformat() if error else None,
    }


def _row_error(row: aiosqlite.Row, *, possibly: bool = False) -> DomainError | None:
    if row["error_code"] is None:
        return None
    return DomainError(
        code=ErrorCode(row["error_code"]),
        stage=ErrorStage(row["error_stage"]),
        category=ErrorCategory(row["error_category"]),
        retryable=bool(row["error_retryable"]),
        retry_after_seconds=row["error_retry_after_seconds"],
        safe_message=row["error_safe_message"],
        provider_request_id=row["error_provider_request_id"],
        possibly_submitted=bool(row["error_possibly_submitted"]) if possibly else False,
        occurred_at=datetime.fromisoformat(row["error_occurred_at"]),
    )
