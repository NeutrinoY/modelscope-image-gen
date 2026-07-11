from __future__ import annotations

from collections.abc import AsyncIterable
from typing import Protocol

from modelscope_image_gen.domain import ImageId, JobId, LocalArtifact


class ArtifactMaterializationError(Exception):
    def __init__(self, error) -> None:
        super().__init__(error.safe_message)
        self.error = error


class ArtifactStore(Protocol):
    def inspect_existing(self, *, job_id: JobId, image_id: ImageId, position: int) -> LocalArtifact | None: ...

    async def save(
        self,
        *,
        job_id: JobId,
        image_id: ImageId,
        position: int,
        chunks: AsyncIterable[bytes],
        content_length: int | None,
    ) -> LocalArtifact: ...

    def resolve_path(self, artifact: LocalArtifact) -> str: ...
