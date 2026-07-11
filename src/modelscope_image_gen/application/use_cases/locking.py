from __future__ import annotations

from collections.abc import Awaitable, Callable

from modelscope_image_gen.application.ports.system import JobLock
from modelscope_image_gen.domain import JobId


class LockedJobUseCase[ResultT]:
    def __init__(self, inner: Callable[[JobId], Awaitable[ResultT]], locks: JobLock) -> None:
        self._inner = inner
        self._locks = locks

    async def __call__(self, job_id: JobId) -> ResultT:
        async with self._locks.hold(str(job_id)):
            return await self._inner(job_id)
