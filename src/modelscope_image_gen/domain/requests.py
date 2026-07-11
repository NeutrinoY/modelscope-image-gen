from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ImageSize:
    width: int = 1024
    height: int = 1024

    def __post_init__(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise ValueError("image width and height must be positive")

    def as_modelscope_value(self) -> str:
        return f"{self.width}x{self.height}"


@dataclass(frozen=True, slots=True)
class GenerationRequest:
    prompt: str
    model: str
    size: ImageSize = ImageSize()
    negative_prompt: str | None = None
    seed: int | None = None

    def __post_init__(self) -> None:
        prompt = self.prompt.strip()
        model = self.model.strip()
        negative = self.negative_prompt.strip() if self.negative_prompt else None
        if not prompt:
            raise ValueError("prompt must not be empty")
        if not model:
            raise ValueError("model must not be empty")
        object.__setattr__(self, "prompt", prompt)
        object.__setattr__(self, "model", model)
        object.__setattr__(self, "negative_prompt", negative or None)
