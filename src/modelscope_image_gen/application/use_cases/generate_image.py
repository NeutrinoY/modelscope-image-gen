from __future__ import annotations

from collections.abc import Callable

from modelscope_image_gen.application.ports.system import Waiter
from modelscope_image_gen.application.ports.use_cases import CheckUseCase, FetchUseCase
from modelscope_image_gen.application.results import GenerateResult
from modelscope_image_gen.application.use_cases.submit_generation import SubmitGeneration
from modelscope_image_gen.domain import GenerationRequest, JobStatus


class GenerateImage:
    def __init__(
        self,
        submit: SubmitGeneration,
        check: CheckUseCase,
        fetch: FetchUseCase,
        wait: Waiter,
        monotonic: Callable[[], float],
        poll_interval_seconds: float,
        default_max_wait_seconds: float,
    ) -> None:
        self._submit = submit
        self._check = check
        self._fetch = fetch
        self._wait = wait
        self._monotonic = monotonic
        self._poll_interval = poll_interval_seconds
        self._default_max_wait = default_max_wait_seconds

    async def __call__(self, request: GenerationRequest, *, max_wait_seconds: float | None = None) -> GenerateResult:
        submitted = await self._submit(request)
        if not submitted.ok or submitted.job is None:
            return GenerateResult(
                ok=False,
                job=submitted.job,
                images=submitted.job.images if submitted.job else (),
                completed=bool(submitted.job and submitted.job.status.is_terminal),
                partial=False,
                error=submitted.error,
            )
        job = submitted.job
        deadline = self._monotonic() + (max_wait_seconds if max_wait_seconds is not None else self._default_max_wait)
        while self._monotonic() < deadline:
            checked = await self._check(job.job_id)
            job = checked.job
            if job.status is JobStatus.FAILED:
                return GenerateResult(
                    ok=False, job=job, images=job.images, completed=True, partial=False, error=job.last_error
                )
            if job.status is JobStatus.SUCCEEDED:
                fetched = await self._fetch(job.job_id)
                return GenerateResult(
                    ok=fetched.ok,
                    job=fetched.job,
                    images=fetched.images,
                    completed=True,
                    partial=fetched.partial,
                    error=fetched.error,
                )
            remaining = deadline - self._monotonic()
            if remaining <= 0:
                break
            await self._wait(min(self._poll_interval, remaining))
        return GenerateResult(ok=True, job=job, images=job.images, completed=False, partial=False)
