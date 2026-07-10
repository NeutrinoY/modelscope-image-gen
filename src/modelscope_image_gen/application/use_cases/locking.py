from __future__ import annotations

from typing import Any


class LockedJobUseCase:
    def __init__(self, inner: Any, locks: Any) -> None:
        self._inner = inner
        self._locks = locks

    async def __call__(self, job_id):
        async with self._locks.hold(str(job_id)):
            return await self._inner(job_id)
