from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime

from .errors import DomainError
from .ids import ArtifactKey, ImageId
from .states import ArtifactStatus


@dataclass(frozen=True, slots=True)
class ProviderImageReference:
    locator: str
    provider_request_id: str | None = None

    def __post_init__(self) -> None:
        if not self.locator:
            raise ValueError("provider image locator must not be empty")


@dataclass(frozen=True, slots=True)
class LocalArtifact:
    artifact_key: ArtifactKey
    file_path: str
    relative_path: str
    sha256: str
    byte_size: int
    media_type: str
    format: str
    width: int
    height: int
    saved_at: datetime

    def __post_init__(self) -> None:
        if self.byte_size <= 0 or self.width <= 0 or self.height <= 0:
            raise ValueError("artifact dimensions and size must be positive")
        if len(self.sha256) != 64:
            raise ValueError("sha256 must contain 64 hexadecimal characters")


@dataclass(frozen=True, slots=True)
class GeneratedImage:
    image_id: ImageId
    position: int
    provider_reference: ProviderImageReference
    artifact_status: ArtifactStatus = ArtifactStatus.PENDING
    local_artifact: LocalArtifact | None = None
    last_error: DomainError | None = None

    def __post_init__(self) -> None:
        if self.position < 0:
            raise ValueError("image position must be non-negative")
        if self.artifact_status is ArtifactStatus.AVAILABLE and self.local_artifact is None:
            raise ValueError("available image requires a local artifact")
        if self.artifact_status is not ArtifactStatus.AVAILABLE and self.local_artifact is not None:
            raise ValueError("non-available image cannot contain a local artifact")
        if self.artifact_status is ArtifactStatus.FAILED and self.last_error is None:
            raise ValueError("failed image requires an error")

    def mark_available(self, artifact: LocalArtifact) -> GeneratedImage:
        if self.artifact_status is ArtifactStatus.AVAILABLE:
            return self
        return replace(self, artifact_status=ArtifactStatus.AVAILABLE, local_artifact=artifact, last_error=None)

    def mark_failed(self, error: DomainError) -> GeneratedImage:
        if self.artifact_status is ArtifactStatus.AVAILABLE:
            return self
        return replace(self, artifact_status=ArtifactStatus.FAILED, local_artifact=None, last_error=error)
