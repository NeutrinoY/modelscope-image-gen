import time
from datetime import UTC, datetime

import anyio
import pytest

from modelscope_image_gen.application.results import CheckResult, FetchResult, SubmitResult
from modelscope_image_gen.application.use_cases.generate_image import GenerateImage
from modelscope_image_gen.domain import GenerationJob, GenerationRequest, JobId

NOW = datetime(2026, 7, 10, tzinfo=UTC)


class Clock:
    value = 0.0

    def monotonic(self) -> float:
        return self.value

    async def wait(self, seconds: float) -> None:
        self.value += seconds


@pytest.mark.anyio
async def test_generate_wait_limit_hands_job_back_without_timeout_state() -> None:
    job = GenerationJob.create_submitting(
        job_id=JobId.new(), request=GenerationRequest(prompt="cat", model="m"), now=NOW
    )
    job = job.mark_submitted(task_id="task", provider_request_id=None, provider_status="PENDING", now=NOW)

    async def submit(_request):
        return SubmitResult(ok=True, job=job, accepted=True)

    async def check(_job_id):
        return CheckResult(ok=True, job=job)

    async def fetch(_job_id):
        return FetchResult(ok=True, job=job, images=(), partial=False)

    clock = Clock()
    use_case = GenerateImage(submit, check, fetch, clock.wait, clock.monotonic, 2, 10)
    result = await use_case(job.request, max_wait_seconds=3)

    assert result.ok is True
    assert result.completed is False
    assert result.job is not None
    assert result.job.status.value == "submitted"


@pytest.mark.anyio
async def test_generate_wait_limit_cancels_an_overlong_check() -> None:
    job = GenerationJob.create_submitting(
        job_id=JobId.new(), request=GenerationRequest(prompt="cat", model="m"), now=NOW
    )
    job = job.mark_submitted(task_id="task", provider_request_id=None, provider_status="PENDING", now=NOW)

    async def submit(_request):
        return SubmitResult(ok=True, job=job, accepted=True)

    async def check(_job_id):
        await anyio.sleep(1)
        return CheckResult(ok=True, job=job)

    async def fetch(_job_id):
        return FetchResult(ok=True, job=job, images=(), partial=False)

    use_case = GenerateImage(submit, check, fetch, anyio.sleep, time.monotonic, 1, 10)
    with anyio.fail_after(0.5):
        result = await use_case(job.request, max_wait_seconds=0.05)

    assert result.ok is True
    assert result.completed is False
    assert result.job == job
