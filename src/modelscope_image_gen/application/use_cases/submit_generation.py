from __future__ import annotations

from modelscope_image_gen.application.ports.provider import ImageGenerationProvider
from modelscope_image_gen.application.ports.system import Clock, JobIdFactory
from modelscope_image_gen.application.provider_outcomes import SubmitAccepted, SubmitRejected, SubmitUnknown
from modelscope_image_gen.application.repositories import GenerationJobRepository
from modelscope_image_gen.application.results import SubmitResult
from modelscope_image_gen.domain import GenerationJob, GenerationRequest


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
        validate = getattr(self._provider, "validate", None)
        validation_error = validate(request) if validate else None
        if validation_error is not None:
            return SubmitResult(ok=False, job=None, accepted=False, error=validation_error)
        now = self._clock()
        stored = await self._repository.add(
            GenerationJob.create_submitting(job_id=self._new_job_id(), request=request, now=now)
        )
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
            return SubmitResult(ok=True, job=saved.job, accepted=True)
        if isinstance(outcome, (SubmitRejected, SubmitUnknown)):
            job = stored.job.mark_submission_failed(error=outcome.error, now=now)
            saved = await self._repository.save(job, expected_revision=stored.revision)
            return SubmitResult(ok=False, job=saved.job, accepted=False, error=outcome.error)
        raise TypeError(f"unsupported submit outcome: {type(outcome)!r}")
