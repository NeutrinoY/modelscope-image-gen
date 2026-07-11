from __future__ import annotations

import logging

import anyio

from modelscope_image_gen.application.ports.artifact_store import ArtifactMaterializationError, ArtifactStore
from modelscope_image_gen.application.ports.provider import ImageGenerationProvider
from modelscope_image_gen.application.ports.system import Clock
from modelscope_image_gen.application.provider_outcomes import ProviderImageError
from modelscope_image_gen.application.repositories import GenerationJobRepository, RepositoryError
from modelscope_image_gen.application.results import FetchResult
from modelscope_image_gen.application.views import GeneratedImageView
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

logger = logging.getLogger("modelscope-image-gen-mcp")


class FetchGenerationResult:
    def __init__(
        self,
        repository: GenerationJobRepository,
        provider: ImageGenerationProvider,
        artifact_store: ArtifactStore,
        clock: Clock,
        max_concurrency: int,
    ) -> None:
        self._repository = repository
        self._provider = provider
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
            return FetchResult(ok=False, job=job, images=self._views(job.images), partial=False, error=error)

        candidates = [image for image in job.images if image.artifact_status is not ArtifactStatus.AVAILABLE]
        if not candidates:
            return FetchResult(ok=True, job=job, images=self._views(job.images), partial=False)

        logger.info("artifact.fetch.started job_id=%s count=%d", job.job_id, len(candidates))
        limiter = anyio.CapacityLimiter(self._max_concurrency)
        save_lock = anyio.Lock()
        current = stored
        persistence_errors: list[RepositoryError] = []

        async def fetch_one(image: GeneratedImage) -> None:
            nonlocal current
            repaired_existing = False
            async with limiter:
                try:
                    artifact = self._artifact_store.inspect_existing(
                        job_id=job.job_id, image_id=image.image_id, position=image.position
                    )
                    if artifact is None:
                        async with self._provider.open_image(image.provider_reference) as stream:
                            artifact = await self._artifact_store.save(
                                job_id=job.job_id,
                                image_id=image.image_id,
                                position=image.position,
                                chunks=stream,
                                content_length=stream.content_length,
                            )
                    else:
                        repaired_existing = True
                    replacement = image.mark_available(artifact)
                except (ArtifactMaterializationError, ProviderImageError) as exc:
                    replacement = image.mark_failed(exc.error)
            # Once bytes have been atomically materialized (or a stable image error is known),
            # finish the corresponding short database transaction even if the caller cancels.
            with anyio.CancelScope(shield=True):
                async with save_lock:
                    updated = current.job.replace_image(replacement, now=self._clock())
                    try:
                        current = await self._repository.save(updated, expected_revision=current.revision)
                    except RepositoryError as exc:
                        persistence_errors.append(exc)
                        task_group.cancel_scope.cancel()
                    else:
                        if replacement.artifact_status is ArtifactStatus.AVAILABLE:
                            artifact = replacement.local_artifact
                            assert artifact is not None
                            if repaired_existing:
                                logger.info(
                                    "artifact.metadata_repaired job_id=%s image_id=%s artifact_key=%s",
                                    job.job_id,
                                    image.image_id,
                                    artifact.artifact_key,
                                )
                            logger.info(
                                "artifact.fetch.succeeded job_id=%s image_id=%s artifact_key=%s",
                                job.job_id,
                                image.image_id,
                                artifact.artifact_key,
                            )
                        else:
                            error = replacement.last_error
                            assert error is not None
                            logger.warning(
                                "artifact.fetch.failed job_id=%s image_id=%s error_code=%s retryable=%s",
                                job.job_id,
                                image.image_id,
                                error.code.value,
                                str(error.retryable).lower(),
                            )

        async with anyio.create_task_group() as task_group:
            for image in candidates:
                task_group.start_soon(fetch_one, image)

        if persistence_errors:
            raise persistence_errors[0]

        available = current.job.available_image_count
        partial = 0 < available < len(current.job.images)
        if available == 0:
            first_error = next((image.last_error for image in current.job.images if image.last_error), None)
            return FetchResult(
                ok=False, job=current.job, images=self._views(current.job.images), partial=False, error=first_error
            )
        return FetchResult(ok=True, job=current.job, images=self._views(current.job.images), partial=partial)

    def _views(self, images: tuple[GeneratedImage, ...]) -> tuple[GeneratedImageView, ...]:
        views: list[GeneratedImageView] = []
        for image in images:
            artifact = image.local_artifact
            views.append(
                GeneratedImageView(
                    image_id=image.image_id,
                    position=image.position,
                    artifact_status=image.artifact_status,
                    file_path=self._artifact_store.resolve_path(artifact) if artifact else None,
                    relative_path=artifact.relative_path if artifact else None,
                    sha256=artifact.sha256 if artifact else None,
                    byte_size=artifact.byte_size if artifact else None,
                    media_type=artifact.media_type if artifact else None,
                    format=artifact.format if artifact else None,
                    width=artifact.width if artifact else None,
                    height=artifact.height if artifact else None,
                    saved_at=artifact.saved_at if artifact else None,
                    last_error=image.last_error,
                )
            )
        return tuple(views)
