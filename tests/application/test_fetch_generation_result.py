from contextlib import asynccontextmanager
from datetime import UTC, datetime

import anyio
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
        self.save_calls = 0
        self.saved = anyio.Event()

    async def get(self, job_id):
        return self.stored

    async def save(self, job, *, expected_revision):
        self.save_calls += 1
        self.stored = StoredGenerationJob(job, expected_revision + 1)
        self.saved.set()
        return self.stored


class Store:
    def __init__(self, fail_position: int | None = None):
        self.fail_position = fail_position
        self.calls: list[int] = []

    def inspect_existing(self, *, job_id, image_id, position):
        return None

    async def save(self, *, job_id, image_id, position, chunks, content_length):
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
            relative_path=f"jobs/{job_id}/{position}.png",
            sha256="a" * 64,
            byte_size=10,
            media_type="image/png",
            format="PNG",
            width=1,
            height=1,
            saved_at=NOW,
        )

    def resolve_path(self, artifact):
        return f"C:/artifacts/{artifact.relative_path}"


class Stream:
    content_length = None

    async def _chunks(self):
        yield b"image"

    def __aiter__(self):
        return self._chunks()


class Provider:
    @asynccontextmanager
    async def open_image(self, reference):
        yield Stream()


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
    result = await FetchGenerationResult(repo, Provider(), store, lambda: NOW, max_concurrency=2)(
        repo.stored.job.job_id
    )

    assert result.ok is True
    assert result.partial is True
    assert result.job.status.value == "succeeded"
    assert [image.artifact_status for image in result.images] == [ArtifactStatus.AVAILABLE, ArtifactStatus.FAILED]
    assert repo.save_calls == 2


@pytest.mark.anyio
async def test_fetch_skips_already_available_images() -> None:
    job = succeeded_job(1)
    first_store = Store()
    repo = Repo(job)
    first = await FetchGenerationResult(repo, Provider(), first_store, lambda: NOW, max_concurrency=1)(job.job_id)
    second_store = Store()
    second = await FetchGenerationResult(repo, Provider(), second_store, lambda: NOW, max_concurrency=1)(job.job_id)

    assert first.ok and second.ok
    assert second_store.calls == []


@pytest.mark.anyio
async def test_fetch_cancellation_keeps_an_already_materialized_image_available() -> None:
    class PartiallyBlockingStore(Store):
        async def save(self, *, job_id, image_id, position, chunks, content_length):
            if position == 1:
                await anyio.sleep_forever()
            return await super().save(
                job_id=job_id,
                image_id=image_id,
                position=position,
                chunks=chunks,
                content_length=content_length,
            )

    repo = Repo(succeeded_job())
    use_case = FetchGenerationResult(repo, Provider(), PartiallyBlockingStore(), lambda: NOW, max_concurrency=2)

    async with anyio.create_task_group() as task_group:
        task_group.start_soon(use_case, repo.stored.job.job_id)
        await repo.saved.wait()
        task_group.cancel_scope.cancel()

    assert repo.stored.job.images[0].artifact_status is ArtifactStatus.AVAILABLE
    assert repo.stored.job.images[1].artifact_status is ArtifactStatus.PENDING
