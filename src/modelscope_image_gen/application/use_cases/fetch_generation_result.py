from __future__ import annotations

import anyio

from modelscope_image_gen.application.ports.artifact_store import ArtifactMaterializationError, ArtifactStore
from modelscope_image_gen.application.ports.system import Clock
from modelscope_image_gen.application.repositories import GenerationJobRepository
from modelscope_image_gen.application.results import FetchResult
from modelscope_image_gen.domain import (
    ArtifactStatus,
    DomainError,
    ErrorCategory,
    ErrorCode,
    ErrorStage,
    GeneratedImage,
    JobId,
    JobStatus,
)


class FetchGenerationResult:
    def __init__(
        self, repository: GenerationJobRepository, artifact_store: ArtifactStore, clock: Clock, max_concurrency: int
    ) -> None:
        self._repository = repository
        self._artifact_store = artifact_store
        self._clock = clock
        self._max_concurrency = max_concurrency

    async def __call__(self, job_id: JobId) -> FetchResult:
        stored = await self._repository.get(job_id)
        if stored is None:
            error = DomainError(
                code=ErrorCode.JOB_NOT_FOUND,
                stage=ErrorStage.VALIDATION,
                category=ErrorCategory.VALIDATION,
                retryable=False,
                safe_message="The requested image generation job was not found.",
                occurred_at=self._clock(),
            )
            raise LookupError(error)
        job = stored.job
        if job.status is not JobStatus.SUCCEEDED:
            error = DomainError(
                code=ErrorCode.RESULT_NOT_READY,
                stage=ErrorStage.ARTIFACT_SAVE,
                category=ErrorCategory.STATE_CONFLICT,
                retryable=job.status in {JobStatus.SUBMITTED, JobStatus.IN_PROGRESS},
                retry_after_seconds=2 if job.status in {JobStatus.SUBMITTED, JobStatus.IN_PROGRESS} else None,
                safe_message="Image artifacts can only be fetched after the job succeeds upstream.",
                occurred_at=self._clock(),
            )
            return FetchResult(ok=False, job=job, images=job.images, partial=False, error=error)

        candidates = [image for image in job.images if image.artifact_status is not ArtifactStatus.AVAILABLE]
        if not candidates:
            return FetchResult(ok=True, job=job, images=job.images, partial=False)

        limiter = anyio.CapacityLimiter(self._max_concurrency)
        replacements: dict[str, GeneratedImage] = {}

        async def fetch_one(image: GeneratedImage) -> None:
            async with limiter:
                try:
                    artifact = await self._artifact_store.materialize(
                        job_id=job.job_id,
                        image_id=image.image_id,
                        position=image.position,
                        reference=image.provider_reference,
                    )
                    replacements[str(image.image_id)] = image.mark_available(artifact)
                except ArtifactMaterializationError as exc:
                    replacements[str(image.image_id)] = image.mark_failed(exc.error)

        async with anyio.create_task_group() as task_group:
            for image in candidates:
                task_group.start_soon(fetch_one, image)

        updated = job
        for image in candidates:
            updated = updated.replace_image(replacements[str(image.image_id)], now=self._clock())
        saved = await self._repository.save(updated, expected_revision=stored.revision)
        available = saved.job.available_image_count
        partial = 0 < available < len(saved.job.images)
        if available == 0:
            first_error = next((image.last_error for image in saved.job.images if image.last_error), None)
            return FetchResult(ok=False, job=saved.job, images=saved.job.images, partial=False, error=first_error)
        return FetchResult(ok=True, job=saved.job, images=saved.job.images, partial=partial)
