from datetime import UTC, datetime

import pytest

from modelscope_image_gen.application.ports.artifact_store import ArtifactMaterializationError
from modelscope_image_gen.application.repositories import StoredGenerationJob
from modelscope_image_gen.application.use_cases.fetch_generation_result import FetchGenerationResult
from modelscope_image_gen.domain import (
    ArtifactKey,
    ArtifactStatus,
    DomainError,
    ErrorCategory,
    ErrorCode,
    ErrorStage,
    GenerationJob,
    GenerationRequest,
    ImageId,
    JobId,
    LocalArtifact,
    ProviderImageReference,
)

NOW = datetime(2026, 7, 10, 12, tzinfo=UTC)


class Repo:
    def __init__(self, job):
        self.stored = StoredGenerationJob(job, 1)

    async def get(self, job_id):
        return self.stored

    async def save(self, job, *, expected_revision):
        self.stored = StoredGenerationJob(job, expected_revision + 1)
        return self.stored


class Store:
    def __init__(self, fail_position: int | None = None):
        self.fail_position = fail_position
        self.calls: list[int] = []

    async def materialize(self, *, job_id, image_id, position, reference):
        self.calls.append(position)
        if position == self.fail_position:
            raise ArtifactMaterializationError(
                DomainError(
                    code=ErrorCode.DOWNLOAD_FAILED,
                    stage=ErrorStage.DOWNLOAD,
                    category=ErrorCategory.NETWORK,
                    retryable=True,
                    safe_message="download failed",
                    occurred_at=NOW,
                )
            )
        return LocalArtifact(
            artifact_key=ArtifactKey(f"jobs/{job_id}/images/{image_id}"),
            file_path=f"C:/artifacts/{position}.png",
            relative_path=f"jobs/{job_id}/{position}.png",
            sha256="a" * 64,
            byte_size=10,
            media_type="image/png",
            format="PNG",
            width=1,
            height=1,
            saved_at=NOW,
        )


def succeeded_job(count: int = 2):
    base = GenerationJob.create_submitting(
        job_id=JobId.new(), request=GenerationRequest(prompt="cat", model="m"), now=NOW
    )
    submitted = base.mark_submitted(task_id="task", provider_request_id=None, provider_status="PENDING", now=NOW)
    return submitted.observe_success(
        references=[ProviderImageReference(f"https://signed/{i}") for i in range(count)],
        image_ids=[ImageId.new() for _ in range(count)],
        provider_status="SUCCEED",
        provider_request_id=None,
        now=NOW,
    )


@pytest.mark.anyio
async def test_fetch_allows_partial_success_and_keeps_job_succeeded() -> None:
    repo = Repo(succeeded_job())
    store = Store(fail_position=1)
    result = await FetchGenerationResult(repo, store, lambda: NOW, max_concurrency=2)(repo.stored.job.job_id)

    assert result.ok is True
    assert result.partial is True
    assert result.job.status.value == "succeeded"
    assert [image.artifact_status for image in result.images] == [ArtifactStatus.AVAILABLE, ArtifactStatus.FAILED]


@pytest.mark.anyio
async def test_fetch_skips_already_available_images() -> None:
    job = succeeded_job(1)
    first_store = Store()
    repo = Repo(job)
    first = await FetchGenerationResult(repo, first_store, lambda: NOW, max_concurrency=1)(job.job_id)
    second_store = Store()
    second = await FetchGenerationResult(repo, second_store, lambda: NOW, max_concurrency=1)(job.job_id)

    assert first.ok and second.ok
    assert second_store.calls == []
