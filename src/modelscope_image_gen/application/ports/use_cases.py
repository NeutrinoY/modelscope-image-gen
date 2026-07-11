from __future__ import annotations

from typing import Protocol

from modelscope_image_gen.application.results import CheckResult, FetchResult
from modelscope_image_gen.domain import JobId


class CheckUseCase(Protocol):
    async def __call__(self, job_id: JobId) -> CheckResult: ...


class FetchUseCase(Protocol):
    async def __call__(self, job_id: JobId) -> FetchResult: ...
