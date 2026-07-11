from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from datetime import datetime
from typing import Protocol

from modelscope_image_gen.domain import ImageId, JobId

Clock = Callable[[], datetime]
JobIdFactory = Callable[[], JobId]
ImageIdFactory = Callable[[], ImageId]


class Waiter(Protocol):
    async def __call__(self, seconds: float) -> None: ...


class JobLock(Protocol):
    def hold(self, job_id: str) -> AbstractAsyncContextManager[None]: ...
