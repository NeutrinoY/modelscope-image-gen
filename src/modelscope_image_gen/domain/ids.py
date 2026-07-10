from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid7


@dataclass(frozen=True, slots=True, order=True)
class JobId:
    value: str

    def __post_init__(self) -> None:
        parsed = UUID(self.value)
        if parsed.version != 7:
            raise ValueError("job_id must be a UUIDv7 string")

    @classmethod
    def new(cls) -> JobId:
        return cls(str(uuid7()))

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True, order=True)
class ImageId:
    value: str

    def __post_init__(self) -> None:
        parsed = UUID(self.value)
        if parsed.version != 7:
            raise ValueError("image_id must be a UUIDv7 string")

    @classmethod
    def new(cls) -> ImageId:
        return cls(str(uuid7()))

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True, order=True)
class ArtifactKey:
    value: str

    def __post_init__(self) -> None:
        if not self.value or self.value.startswith(("/", "\\")) or ".." in self.value.replace("\\", "/").split("/"):
            raise ValueError("artifact key must be a safe relative path")

    def __str__(self) -> str:
        return self.value
