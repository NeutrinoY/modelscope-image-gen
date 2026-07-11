from __future__ import annotations

from datetime import UTC, datetime

import pytest

from modelscope_image_gen.application.provider_outcomes import (
    ProviderRunning,
    ProviderSucceeded,
    SubmitAccepted,
    SubmitUnknown,
)
from modelscope_image_gen.application.repositories import StoredGenerationJob
from modelscope_image_gen.application.use_cases.check_generation import CheckGeneration
from modelscope_image_gen.application.use_cases.submit_generation import SubmitGeneration
from modelscope_image_gen.domain import (
    DomainError,
    ErrorCategory,
    ErrorCode,
    ErrorStage,
    GenerationRequest,
    ImageId,
    JobId,
    JobStatus,
    ProviderImageReference,
)

NOW = datetime(2026, 7, 10, 12, tzinfo=UTC)


class MemoryRepository:
    def __init__(self) -> None:
        self.item: StoredGenerationJob | None = None
        self.events: list[str] = []

    async def add(self, job):
        self.events.append(f"add:{job.status}")
        self.item = StoredGenerationJob(job, 0)
        return self.item

    async def get(self, job_id):
        return self.item if self.item and self.item.job.job_id == job_id else None

    async def save(self, job, *, expected_revision):
        self.events.append(f"save:{job.status}")
        assert self.item is not None and self.item.revision == expected_revision
        self.item = StoredGenerationJob(job, expected_revision + 1)
        return self.item


class Provider:
    def __init__(self, outcome) -> None:
        self.outcome = outcome
        self.calls = 0
        self.repo: MemoryRepository | None = None

    def validate(self, request):
        return None

    async def submit(self, request):
        self.calls += 1
        assert self.repo is not None
        assert self.repo.item is not None
        assert self.repo.item.job.status is JobStatus.SUBMITTING
        return self.outcome

    async def check(self, task):
        self.calls += 1
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


def clock() -> datetime:
    return NOW


def job_id_factory() -> JobId:
    return JobId.new()


def image_id_factory() -> ImageId:
    return ImageId.new()


@pytest.mark.anyio
async def test_submit_persists_intent_before_external_call() -> None:
    repo = MemoryRepository()
    provider = Provider(SubmitAccepted(task_id="task-1", provider_request_id="req", provider_status="PENDING"))
    provider.repo = repo
    use_case = SubmitGeneration(repository=repo, provider=provider, clock=clock, new_job_id=job_id_factory)

    result = await use_case(GenerationRequest(prompt="cat", model="m"))

    assert result.ok is True
    assert result.job.status is JobStatus.SUBMITTED
    assert repo.events == ["add:submitting", "save:submitted"]
    assert provider.calls == 1


@pytest.mark.anyio
async def test_uncertain_submit_is_failed_and_never_retried() -> None:
    err = DomainError(
        code=ErrorCode.SUBMISSION_OUTCOME_UNKNOWN,
        stage=ErrorStage.SUBMIT,
        category=ErrorCategory.NETWORK,
        retryable=False,
        possibly_submitted=True,
        safe_message="Outcome unknown.",
        occurred_at=NOW,
    )
    repo = MemoryRepository()
    provider = Provider(SubmitUnknown(err))
    provider.repo = repo
    use_case = SubmitGeneration(repository=repo, provider=provider, clock=clock, new_job_id=job_id_factory)

    result = await use_case(GenerationRequest(prompt="cat", model="m"))

    assert result.ok is False
    assert result.accepted is False
    assert result.job.status is JobStatus.FAILED
    assert result.error is err
    assert provider.calls == 1


@pytest.mark.anyio
async def test_check_success_creates_all_provider_images() -> None:
    repo = MemoryRepository()
    submit_provider = Provider(SubmitAccepted(task_id="task", provider_request_id=None, provider_status="PENDING"))
    submit_provider.repo = repo
    submitted = await SubmitGeneration(repo, submit_provider, clock, job_id_factory)(
        GenerationRequest(prompt="cat", model="m")
    )

    check_provider = Provider(
        ProviderSucceeded(
            references=(ProviderImageReference("https://signed/1"), ProviderImageReference("https://signed/2")),
            provider_request_id="req-2",
            provider_status="SUCCEED",
        )
    )
    use_case = CheckGeneration(repo, check_provider, clock, image_id_factory)
    result = await use_case(submitted.job.job_id)

    assert result.ok is True
    assert result.job.status is JobStatus.SUCCEEDED
    assert len(result.job.images) == 2


@pytest.mark.anyio
async def test_check_running_updates_state_once() -> None:
    repo = MemoryRepository()
    submit_provider = Provider(SubmitAccepted(task_id="task", provider_request_id=None, provider_status="PENDING"))
    submit_provider.repo = repo
    submitted = await SubmitGeneration(repo, submit_provider, clock, job_id_factory)(
        GenerationRequest(prompt="cat", model="m")
    )

    check_provider = Provider(ProviderRunning(provider_request_id=None, provider_status="PROCESSING"))
    result = await CheckGeneration(repo, check_provider, clock, image_id_factory)(submitted.job.job_id)

    assert result.job.status is JobStatus.IN_PROGRESS
    assert check_provider.calls == 1
