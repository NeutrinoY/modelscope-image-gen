from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, replace
from datetime import datetime

from .artifacts import GeneratedImage, ProviderImageReference
from .errors import DomainError, ErrorCategory, ErrorCode, ErrorStage
from .ids import ImageId, JobId, ProviderName
from .requests import GenerationRequest
from .states import ArtifactAggregateStatus, ArtifactStatus, JobStatus


@dataclass(frozen=True, slots=True)
class ProviderTaskReference:
    task_id: str
    provider_request_id: str | None = None
    last_provider_status: str | None = None
    provider: ProviderName = ProviderName.MODELSCOPE

    def __post_init__(self) -> None:
        task_id = self.task_id.strip()
        if not task_id:
            raise ValueError("provider task_id must not be empty")
        object.__setattr__(self, "task_id", task_id)


@dataclass(frozen=True, slots=True)
class GenerationJob:
    job_id: JobId
    request: GenerationRequest
    status: JobStatus
    provider_task: ProviderTaskReference | None
    images: tuple[GeneratedImage, ...]
    last_error: DomainError | None
    created_at: datetime
    updated_at: datetime
    submitted_at: datetime | None = None
    completed_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.updated_at < self.created_at:
            raise ValueError("updated_at cannot precede created_at")
        if self.status is JobStatus.SUBMITTING:
            if self.provider_task is not None or self.images or self.submitted_at or self.completed_at:
                raise ValueError("submitting job cannot contain provider task, images, or terminal timestamps")
        elif self.status in {JobStatus.SUBMITTED, JobStatus.IN_PROGRESS}:
            if self.provider_task is None or self.images or self.submitted_at is None or self.completed_at is not None:
                raise ValueError("active job requires provider task/submitted_at and cannot contain images")
        elif self.status is JobStatus.SUCCEEDED:
            if self.provider_task is None or not self.images or self.submitted_at is None or self.completed_at is None:
                raise ValueError("succeeded job requires provider task, timestamps, and images")
        elif self.status is JobStatus.FAILED:
            if self.last_error is None or self.completed_at is None:
                raise ValueError("failed job requires error and completed_at")
        positions = [image.position for image in self.images]
        if positions != list(range(len(positions))):
            raise ValueError("image positions must be contiguous and ordered from zero")
        if len({str(image.image_id) for image in self.images}) != len(self.images):
            raise ValueError("image ids must be unique")

    @classmethod
    def create_submitting(cls, *, job_id: JobId, request: GenerationRequest, now: datetime) -> GenerationJob:
        return cls(
            job_id=job_id,
            request=request,
            status=JobStatus.SUBMITTING,
            provider_task=None,
            images=(),
            last_error=None,
            created_at=now,
            updated_at=now,
        )

    @property
    def artifact_status(self) -> ArtifactAggregateStatus:
        if self.status is not JobStatus.SUCCEEDED:
            return ArtifactAggregateStatus.NOT_READY
        available = sum(image.artifact_status is ArtifactStatus.AVAILABLE for image in self.images)
        failed = sum(image.artifact_status is ArtifactStatus.FAILED for image in self.images)
        if available == len(self.images):
            return ArtifactAggregateStatus.AVAILABLE
        if available:
            return ArtifactAggregateStatus.PARTIAL
        if failed == len(self.images):
            return ArtifactAggregateStatus.FAILED
        return ArtifactAggregateStatus.PENDING

    @property
    def available_image_count(self) -> int:
        return sum(image.artifact_status is ArtifactStatus.AVAILABLE for image in self.images)

    def mark_submitted(
        self, *, task_id: str, provider_request_id: str | None, provider_status: str | None, now: datetime
    ) -> GenerationJob:
        self._require_status(JobStatus.SUBMITTING)
        return replace(
            self,
            status=JobStatus.SUBMITTED,
            provider_task=ProviderTaskReference(task_id, provider_request_id, provider_status),
            last_error=None,
            submitted_at=now,
            updated_at=now,
        )

    def mark_submission_failed(self, *, error: DomainError, now: datetime) -> GenerationJob:
        self._require_status(JobStatus.SUBMITTING)
        return replace(self, status=JobStatus.FAILED, last_error=error, completed_at=now, updated_at=now)

    def observe_pending(self, *, provider_status: str, provider_request_id: str | None, now: datetime) -> GenerationJob:
        self._require_status(JobStatus.SUBMITTED, JobStatus.IN_PROGRESS)
        task = self._updated_provider_task(provider_status, provider_request_id)
        return replace(self, provider_task=task, last_error=None, updated_at=now)

    def observe_running(self, *, provider_status: str, provider_request_id: str | None, now: datetime) -> GenerationJob:
        self._require_status(JobStatus.SUBMITTED, JobStatus.IN_PROGRESS)
        task = self._updated_provider_task(provider_status, provider_request_id)
        return replace(self, status=JobStatus.IN_PROGRESS, provider_task=task, last_error=None, updated_at=now)

    def observe_success(
        self,
        *,
        references: Iterable[ProviderImageReference],
        image_ids: Iterable[ImageId],
        provider_status: str,
        provider_request_id: str | None,
        now: datetime,
    ) -> GenerationJob:
        self._require_status(JobStatus.SUBMITTED, JobStatus.IN_PROGRESS)
        refs = tuple(references)
        ids = tuple(image_ids)
        if not refs:
            error = DomainError(
                code=ErrorCode.EMPTY_OUTPUT_IMAGES,
                stage=ErrorStage.STATUS_CHECK,
                category=ErrorCategory.UPSTREAM_CONTRACT,
                retryable=False,
                safe_message="ModelScope reported success without any image results.",
                occurred_at=now,
                provider_request_id=provider_request_id,
            )
            return self.observe_failure(
                error=error, provider_status=provider_status, provider_request_id=provider_request_id, now=now
            )
        if len(refs) != len(ids):
            raise ValueError("one image id is required for each provider image reference")
        images = tuple(
            GeneratedImage(image_id=image_id, position=index, provider_reference=ref)
            for index, (image_id, ref) in enumerate(zip(ids, refs, strict=True))
        )
        task = self._updated_provider_task(provider_status, provider_request_id)
        return replace(
            self,
            status=JobStatus.SUCCEEDED,
            provider_task=task,
            images=images,
            last_error=None,
            completed_at=now,
            updated_at=now,
        )

    def observe_failure(
        self, *, error: DomainError, provider_status: str, provider_request_id: str | None, now: datetime
    ) -> GenerationJob:
        self._require_status(JobStatus.SUBMITTED, JobStatus.IN_PROGRESS)
        task = self._updated_provider_task(provider_status, provider_request_id)
        return replace(
            self, status=JobStatus.FAILED, provider_task=task, last_error=error, completed_at=now, updated_at=now
        )

    def record_operation_error(self, *, error: DomainError, now: datetime) -> GenerationJob:
        if self.status.is_terminal:
            return self
        return replace(self, last_error=error, updated_at=now)

    def record_provider_observation_error(
        self,
        *,
        error: DomainError,
        provider_status: str,
        provider_request_id: str | None,
        now: datetime,
    ) -> GenerationJob:
        self._require_status(JobStatus.SUBMITTED, JobStatus.IN_PROGRESS)
        task = self._updated_provider_task(provider_status, provider_request_id)
        return replace(self, provider_task=task, last_error=error, updated_at=now)

    def replace_image(self, image: GeneratedImage, *, now: datetime) -> GenerationJob:
        if self.status is not JobStatus.SUCCEEDED:
            raise self._transition_error("artifacts can only change for a succeeded job", now)
        images = list(self.images)
        try:
            index = next(i for i, current in enumerate(images) if current.image_id == image.image_id)
        except StopIteration as exc:
            raise ValueError("image does not belong to job") from exc
        images[index] = image
        return replace(self, images=tuple(images), updated_at=now)

    def _updated_provider_task(self, provider_status: str, provider_request_id: str | None) -> ProviderTaskReference:
        if self.provider_task is None:
            raise ValueError("provider task reference is missing")
        return replace(
            self.provider_task,
            provider_request_id=provider_request_id or self.provider_task.provider_request_id,
            last_provider_status=provider_status,
        )

    def _require_status(self, *allowed: JobStatus) -> None:
        if self.status not in allowed:
            raise ValueError(f"invalid job transition from {self.status}")

    def _transition_error(self, message: str, now: datetime) -> ValueError:
        return ValueError(f"{ErrorCode.INVALID_JOB_TRANSITION}: {message} at {now.isoformat()}")
