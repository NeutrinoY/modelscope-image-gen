from datetime import UTC, datetime

import pytest

from modelscope_image_gen.application.repositories import JobListQuery, RepositoryError
from modelscope_image_gen.domain import GenerationJob, GenerationRequest, JobId, JobStatus
from modelscope_image_gen.infrastructure.sqlite.repository import SqliteGenerationJobRepository


@pytest.mark.anyio
async def test_sqlite_round_trip_and_optimistic_revision(tmp_path) -> None:
    repo = await SqliteGenerationJobRepository.open(tmp_path / "jobs.sqlite3")
    try:
        now = datetime(2026, 7, 10, tzinfo=UTC)
        job = GenerationJob.create_submitting(
            job_id=JobId.new(), request=GenerationRequest(prompt="cat", model="m"), now=now
        )
        stored = await repo.add(job)
        assert stored.revision == 0

        submitted = job.mark_submitted(task_id="task", provider_request_id="req", provider_status="PENDING", now=now)
        saved = await repo.save(submitted, expected_revision=0)
        loaded = await repo.get(job.job_id)

        assert saved.revision == 1
        assert loaded is not None
        assert loaded.job == submitted
        assert loaded.revision == 1
        page = await repo.list(JobListQuery(statuses=(JobStatus.SUBMITTED,), limit=20))
        assert [item.job_id for item in page.items] == [job.job_id]
    finally:
        await repo.close()


@pytest.mark.anyio
async def test_stale_revision_is_rejected(tmp_path) -> None:
    repo = await SqliteGenerationJobRepository.open(tmp_path / "jobs.sqlite3")
    try:
        now = datetime(2026, 7, 10, tzinfo=UTC)
        job = GenerationJob.create_submitting(
            job_id=JobId.new(), request=GenerationRequest(prompt="cat", model="m"), now=now
        )
        await repo.add(job)
        submitted = job.mark_submitted(task_id="task", provider_request_id=None, provider_status="PENDING", now=now)
        await repo.save(submitted, expected_revision=0)
        with pytest.raises(RepositoryError) as raised:
            await repo.save(submitted, expected_revision=0)
        assert raised.value.error.code.value == "CONCURRENT_MODIFICATION"
    finally:
        await repo.close()
