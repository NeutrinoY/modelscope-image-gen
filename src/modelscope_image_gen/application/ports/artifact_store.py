from __future__ import annotations

from typing import Protocol

from modelscope_image_gen.domain import ImageId, JobId, LocalArtifact, ProviderImageReference


class ArtifactMaterializationError(Exception):
    def __init__(self, error) -> None:
        super().__init__(error.safe_message)
        self.error = error


class ArtifactStore(Protocol):
    async def materialize(
        self,
        *,
        job_id: JobId,
        image_id: ImageId,
        position: int,
        reference: ProviderImageReference,
    ) -> LocalArtifact: ...
