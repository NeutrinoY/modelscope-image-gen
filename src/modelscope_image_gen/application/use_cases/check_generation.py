from __future__ import annotations

import logging

from modelscope_image_gen.application.ports.provider import ImageGenerationProvider
from modelscope_image_gen.application.ports.system import Clock, ImageIdFactory
from modelscope_image_gen.application.provider_outcomes import (
    ProviderFailed,
    ProviderPending,
    ProviderRunning,
    ProviderSucceeded,
    ProviderTemporaryError,
    ProviderUnknownStatus,
)
from modelscope_image_gen.application.repositories import GenerationJobRepository
from modelscope_image_gen.application.results import CheckResult
from modelscope_image_gen.domain import DomainError, ErrorCategory, ErrorCode, ErrorStage, JobId, JobStatus

logger = logging.getLogger("modelscope-image-gen-mcp")


class CheckGeneration:
    def __init__(
        self,
        repository: GenerationJobRepository,
        provider: ImageGenerationProvider,
        clock: Clock,
        new_image_id: ImageIdFactory,
    ) -> None:
        self._repository = repository
        self._provider = provider
        self._clock = clock
        self._new_image_id = new_image_id

    async def __call__(self, job_id: JobId) -> CheckResult:
        stored = await self._repository.get(job_id)
        if stored is None:
            now = self._clock()
            error = DomainError(
                code=ErrorCode.JOB_NOT_FOUND,
                stage=ErrorStage.VALIDATION,
                category=ErrorCategory.VALIDATION,
                retryable=False,
                safe_message="The requested image generation job was not found.",
                occurred_at=now,
            )
            raise LookupError(error)
        job = stored.job
        if job.status.is_terminal:
            logger.info("job.status.checked job_id=%s status=%s source=local", job.job_id, job.status.value)
            return CheckResult(ok=True, job=job)
        if job.status is JobStatus.SUBMITTING:
            error = DomainError(
                code=ErrorCode.SUBMISSION_OUTCOME_UNKNOWN,
                stage=ErrorStage.SUBMIT,
                category=ErrorCategory.STATE_CONFLICT,
                retryable=False,
                possibly_submitted=True,
                safe_message="The submission outcome is unknown because no reliable task identifier was recorded.",
                occurred_at=self._clock(),
            )
            failed = job.mark_submission_failed(error=error, now=self._clock())
            saved = await self._repository.save(failed, expected_revision=stored.revision)
            logger.warning(
                "job.submit.uncertain job_id=%s error_code=%s possibly_submitted=true",
                saved.job.job_id,
                error.code.value,
            )
            return CheckResult(ok=False, job=saved.job, error=error)
        assert job.provider_task is not None
        try:
            outcome = await self._provider.check(job.provider_task)
        except ProviderTemporaryError as exc:
            updated = job.record_operation_error(error=exc.error, now=self._clock())
            saved = await self._repository.save(updated, expected_revision=stored.revision)
            logger.warning(
                "job.status.check_failed job_id=%s error_code=%s retryable=%s",
                saved.job.job_id,
                exc.error.code.value,
                str(exc.error.retryable).lower(),
            )
            return CheckResult(ok=False, job=saved.job, error=exc.error)
        now = self._clock()
        if isinstance(outcome, ProviderPending):
            updated = job.observe_pending(
                provider_status=outcome.provider_status, provider_request_id=outcome.provider_request_id, now=now
            )
            result_error = None
        elif isinstance(outcome, ProviderRunning):
            updated = job.observe_running(
                provider_status=outcome.provider_status, provider_request_id=outcome.provider_request_id, now=now
            )
            result_error = None
        elif isinstance(outcome, ProviderSucceeded):
            ids = tuple(self._new_image_id() for _ in outcome.references)
            updated = job.observe_success(
                references=outcome.references,
                image_ids=ids,
                provider_status=outcome.provider_status,
                provider_request_id=outcome.provider_request_id,
                now=now,
            )
            result_error = updated.last_error if updated.status is JobStatus.FAILED else None
        elif isinstance(outcome, ProviderFailed):
            updated = job.observe_failure(
                error=outcome.error,
                provider_status=outcome.provider_status,
                provider_request_id=outcome.provider_request_id,
                now=now,
            )
            result_error = None
        elif isinstance(outcome, ProviderUnknownStatus):
            updated = job.record_provider_observation_error(
                error=outcome.error,
                provider_status=outcome.provider_status,
                provider_request_id=outcome.provider_request_id,
                now=now,
            )
            result_error = outcome.error
        else:
            raise TypeError(f"unsupported provider outcome: {type(outcome)!r}")
        saved = await self._repository.save(updated, expected_revision=stored.revision)
        if result_error is None:
            logger.info(
                "job.status.checked job_id=%s status=%s source=provider", saved.job.job_id, saved.job.status.value
            )
        else:
            logger.warning(
                "job.status.check_failed job_id=%s error_code=%s retryable=%s",
                saved.job.job_id,
                result_error.code.value,
                str(result_error.retryable).lower(),
            )
        if saved.job.status is not job.status:
            logger.info(
                "job.status.changed job_id=%s from_status=%s to_status=%s",
                saved.job.job_id,
                job.status.value,
                saved.job.status.value,
            )
        return CheckResult(ok=result_error is None, job=saved.job, error=result_error)
