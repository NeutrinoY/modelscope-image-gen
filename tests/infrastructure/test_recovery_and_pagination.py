from datetime import UTC, datetime, timedelta

import pytest

from modelscope_image_gen.application.repositories import JobListQuery
from modelscope_image_gen.domain import GenerationJob, GenerationRequest, JobId, JobStatus
from modelscope_image_gen.infrastructure.sqlite.repository import SqliteGenerationJobRepository


@pytest.mark.anyio
async def test_startup_recovery_marks_stale_submitting_as_uncertain(tmp_path) -> None:
    database = tmp_path / "state.sqlite3"
    repo = await SqliteGenerationJobRepository.open(database)
    now = datetime(2026, 7, 10, tzinfo=UTC)
    job = GenerationJob.create_submitting(
        job_id=JobId.new(), request=GenerationRequest(prompt="cat", model="m"), now=now
    )
    await repo.add(job)
    await repo.close()

    reopened = await SqliteGenerationJobRepository.open(database)
    try:
        assert await reopened.recover_stale_submitting() == 1
        recovered = await reopened.get(job.job_id)
        assert recovered is not None
        assert recovered.job.status is JobStatus.FAILED
        assert recovered.job.last_error is not None
        assert recovered.job.last_error.possibly_submitted is True
    finally:
        await reopened.close()


@pytest.mark.anyio
async def test_list_uses_opaque_keyset_cursor(tmp_path) -> None:
    repo = await SqliteGenerationJobRepository.open(tmp_path / "state.sqlite3")
    try:
        now = datetime(2026, 7, 10, tzinfo=UTC)
        jobs = [
            GenerationJob.create_submitting(
                job_id=JobId.new(),
                request=GenerationRequest(prompt=f"cat {index}", model="m"),
                now=now + timedelta(seconds=index),
            )
            for index in range(3)
        ]
        for job in jobs:
            await repo.add(job)
        first = await repo.list(JobListQuery(limit=2))
        second = await repo.list(JobListQuery(limit=2, cursor=first.next_cursor))
        assert len(first.items) == 2
        assert not hasattr(first.items[0], "job")
        assert first.next_cursor is not None
        assert len(second.items) == 1
        assert {item.job_id for item in first.items}.isdisjoint({item.job_id for item in second.items})
    finally:
        await repo.close()
