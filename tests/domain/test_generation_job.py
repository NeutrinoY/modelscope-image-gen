from datetime import UTC, datetime, timedelta

import pytest

from modelscope_image_gen.domain import (
    ArtifactStatus,
    DomainError,
    ErrorCategory,
    ErrorCode,
    ErrorStage,
    GeneratedImage,
    GenerationJob,
    GenerationRequest,
    ImageId,
    JobId,
    JobStatus,
    LocalArtifact,
    ProviderImageReference,
)
from modelscope_image_gen.domain.ids import ArtifactKey


def now() -> datetime:
    return datetime(2026, 7, 10, 12, tzinfo=UTC)


def error(code: ErrorCode = ErrorCode.SUBMISSION_REJECTED) -> DomainError:
    return DomainError(
        code=code,
        stage=ErrorStage.SUBMIT,
        category=ErrorCategory.UPSTREAM_HTTP,
        retryable=False,
        safe_message="safe",
        occurred_at=now(),
    )


def test_submit_state_machine_and_success_images() -> None:
    job = GenerationJob.create_submitting(
        job_id=JobId.new(), request=GenerationRequest(prompt="cat", model="m"), now=now()
    )
    assert job.status is JobStatus.SUBMITTING

    submitted = job.mark_submitted(task_id="task-1", provider_request_id="req-1", provider_status="PENDING", now=now())
    running = submitted.observe_running(
        provider_status="RUNNING", provider_request_id="req-2", now=now() + timedelta(seconds=1)
    )
    succeeded = running.observe_success(
        references=[ProviderImageReference("https://signed/1"), ProviderImageReference("https://signed/2")],
        image_ids=[ImageId.new(), ImageId.new()],
        provider_status="SUCCEED",
        provider_request_id="req-3",
        now=now() + timedelta(seconds=2),
    )

    assert succeeded.status is JobStatus.SUCCEEDED
    assert [image.position for image in succeeded.images] == [0, 1]
    assert all(image.artifact_status is ArtifactStatus.PENDING for image in succeeded.images)


def test_timeout_is_not_a_job_status_and_transient_error_preserves_state() -> None:
    job = GenerationJob.create_submitting(
        job_id=JobId.new(), request=GenerationRequest(prompt="cat", model="m"), now=now()
    )
    submitted = job.mark_submitted(task_id="task-1", provider_request_id=None, provider_status="PENDING", now=now())
    transient = DomainError(
        code=ErrorCode.NETWORK_ERROR,
        stage=ErrorStage.STATUS_CHECK,
        category=ErrorCategory.NETWORK,
        retryable=True,
        retry_after_seconds=2,
        safe_message="Status could not be refreshed.",
        occurred_at=now(),
    )

    updated = submitted.record_operation_error(error=transient, now=now() + timedelta(seconds=1))
    assert updated.status is JobStatus.SUBMITTED
    assert "timeout" not in {status.value for status in JobStatus}


def test_artifact_failure_does_not_change_succeeded_job() -> None:
    base = GenerationJob.create_submitting(
        job_id=JobId.new(), request=GenerationRequest(prompt="cat", model="m"), now=now()
    )
    submitted = base.mark_submitted(task_id="task", provider_request_id=None, provider_status="PENDING", now=now())
    job = submitted.observe_success(
        references=[ProviderImageReference("https://signed/1")],
        image_ids=[ImageId.new()],
        provider_status="SUCCEED",
        provider_request_id=None,
        now=now(),
    )
    failed = job.images[0].mark_failed(error(ErrorCode.DOWNLOAD_FAILED))
    updated = job.replace_image(failed, now=now())

    assert updated.status is JobStatus.SUCCEEDED
    assert updated.images[0].artifact_status is ArtifactStatus.FAILED


def test_available_image_requires_valid_artifact() -> None:
    artifact = LocalArtifact(
        artifact_key=ArtifactKey("job/image.png"),
        relative_path="job/image.png",
        sha256="a" * 64,
        byte_size=10,
        media_type="image/png",
        format="PNG",
        width=1,
        height=1,
        saved_at=now(),
    )
    image = GeneratedImage(
        image_id=ImageId.new(), position=0, provider_reference=ProviderImageReference("https://signed/1")
    )
    assert image.mark_available(artifact).artifact_status is ArtifactStatus.AVAILABLE


def test_local_artifact_rejects_unsafe_relative_path() -> None:
    with pytest.raises(ValueError, match="relative_path"):
        LocalArtifact(
            artifact_key=ArtifactKey("job/image.png"),
            relative_path="../outside.png",
            sha256="a" * 64,
            byte_size=10,
            media_type="image/png",
            format="PNG",
            width=1,
            height=1,
            saved_at=now(),
        )


def test_illegal_transition_is_rejected() -> None:
    job = GenerationJob.create_submitting(
        job_id=JobId.new(), request=GenerationRequest(prompt="cat", model="m"), now=now()
    )
    with pytest.raises(ValueError):
        job.observe_running(provider_status="RUNNING", provider_request_id=None, now=now())
