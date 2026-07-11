from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID, uuid7


class ProviderName(StrEnum):
    MODELSCOPE = "modelscope"


@dataclass(frozen=True, slots=True, order=True)
class JobId:
    value: str

    def __post_init__(self) -> None:
        parsed = UUID(self.value)
        if parsed.version != 7 or self.value != str(parsed):
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
        if parsed.version != 7 or self.value != str(parsed):
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
        parts = self.value.split("/")
        if (
            not self.value
            or self.value.startswith("/")
            or "\\" in self.value
            or any(not part or part in {".", ".."} or ":" in part for part in parts)
        ):
            raise ValueError("artifact key must be a safe relative path")

    def __str__(self) -> str:
        return self.value
