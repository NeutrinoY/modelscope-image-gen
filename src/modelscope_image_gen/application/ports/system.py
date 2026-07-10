from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Protocol

from modelscope_image_gen.domain import ImageId, JobId

Clock = Callable[[], datetime]
JobIdFactory = Callable[[], JobId]
ImageIdFactory = Callable[[], ImageId]


class Waiter(Protocol):
    async def __call__(self, seconds: float) -> None: ...
