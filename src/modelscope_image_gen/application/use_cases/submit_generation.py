from __future__ import annotations

import logging

from modelscope_image_gen.application.ports.provider import ImageGenerationProvider
from modelscope_image_gen.application.ports.system import Clock, JobIdFactory
from modelscope_image_gen.application.provider_outcomes import SubmitAccepted, SubmitRejected, SubmitUnknown
from modelscope_image_gen.application.repositories import GenerationJobRepository
from modelscope_image_gen.application.results import SubmitResult
from modelscope_image_gen.domain import GenerationJob, GenerationRequest

logger = logging.getLogger("modelscope-image-gen-mcp")


class SubmitGeneration:
    def __init__(
        self,
        repository: GenerationJobRepository,
        provider: ImageGenerationProvider,
        clock: Clock,
        new_job_id: JobIdFactory,
    ) -> None:
        self._repository = repository
        self._provider = provider
        self._clock = clock
        self._new_job_id = new_job_id

    async def __call__(self, request: GenerationRequest) -> SubmitResult:
        validation_error = self._provider.validate(request)
        if validation_error is not None:
            logger.info("job.submit.failed error_code=%s", validation_error.code.value)
            return SubmitResult(ok=False, job=None, accepted=False, error=validation_error)
        now = self._clock()
        job = GenerationJob.create_submitting(job_id=self._new_job_id(), request=request, now=now)
        logger.info("job.submit.started job_id=%s", job.job_id)
        stored = await self._repository.add(job)
        outcome = await self._provider.submit(request)
        now = self._clock()
        if isinstance(outcome, SubmitAccepted):
            job = stored.job.mark_submitted(
                task_id=outcome.task_id,
                provider_request_id=outcome.provider_request_id,
                provider_status=outcome.provider_status,
                now=now,
            )
            saved = await self._repository.save(job, expected_revision=stored.revision)
            logger.info("job.submit.succeeded job_id=%s", saved.job.job_id)
            return SubmitResult(ok=True, job=saved.job, accepted=True)
        if isinstance(outcome, (SubmitRejected, SubmitUnknown)):
            job = stored.job.mark_submission_failed(error=outcome.error, now=now)
            saved = await self._repository.save(job, expected_revision=stored.revision)
            event = "job.submit.uncertain" if isinstance(outcome, SubmitUnknown) else "job.submit.failed"
            logger.warning(
                "%s job_id=%s error_code=%s retryable=%s possibly_submitted=%s",
                event,
                saved.job.job_id,
                outcome.error.code.value,
                str(outcome.error.retryable).lower(),
                str(outcome.error.possibly_submitted).lower(),
            )
            return SubmitResult(ok=False, job=saved.job, accepted=False, error=outcome.error)
        raise TypeError(f"unsupported submit outcome: {type(outcome)!r}")
