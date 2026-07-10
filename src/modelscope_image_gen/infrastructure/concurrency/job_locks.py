from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

import anyio


@dataclass(slots=True)
class _Entry:
    lock: anyio.Lock
    users: int = 0


class JobLockManager:
    def __init__(self) -> None:
        self._guard = anyio.Lock()
        self._entries: dict[str, _Entry] = {}

    @asynccontextmanager
    async def hold(self, job_id: str) -> AsyncIterator[None]:
        async with self._guard:
            entry = self._entries.get(job_id)
            if entry is None:
                entry = _Entry(anyio.Lock())
                self._entries[job_id] = entry
            entry.users += 1
        try:
            async with entry.lock:
                yield
        finally:
            async with self._guard:
                entry.users -= 1
                if entry.users == 0 and not entry.lock.locked():
                    self._entries.pop(job_id, None)

    @property
    def active_key_count(self) -> int:
        return len(self._entries)
