from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator

from modelscope_image_gen.domain import JobId, JobStatus


class StrictInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ImageSizeInput(StrictInput):
    width: int = Field(default=1024, gt=0)
    height: int = Field(default=1024, gt=0)


class SubmitImageGenerationInput(StrictInput):
    prompt: str = Field(min_length=1)
    model: str | None = None
    size: ImageSizeInput = Field(default_factory=ImageSizeInput)
    negative_prompt: str | None = None
    seed: int | None = None

    @field_validator("prompt")
    @classmethod
    def normalize_prompt(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("prompt must not be empty")
        return value

    @field_validator("model")
    @classmethod
    def normalize_model(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("model must not be empty")
        return value

    @field_validator("negative_prompt")
    @classmethod
    def normalize_negative_prompt(cls, value: str | None) -> str | None:
        return value.strip() or None if value else None


class CheckImageGenerationInput(StrictInput):
    job_id: str = Field(min_length=1)

    @field_validator("job_id")
    @classmethod
    def validate_job_id(cls, value: str) -> str:
        return str(JobId(value.strip()))


class FetchImageGenerationResultInput(StrictInput):
    job_id: str = Field(min_length=1)

    @field_validator("job_id")
    @classmethod
    def validate_job_id(cls, value: str) -> str:
        return str(JobId(value.strip()))


class ListImageGenerationsInput(StrictInput):
    statuses: list[JobStatus] | None = None
    limit: int = Field(default=20, ge=1, le=100)
    cursor: str | None = None

    @field_validator("statuses")
    @classmethod
    def normalize_statuses(cls, value: list[JobStatus] | None) -> list[JobStatus] | None:
        if not value:
            return None
        order = {status: index for index, status in enumerate(JobStatus)}
        return sorted(set(value), key=order.__getitem__)


class GenerateImageInput(SubmitImageGenerationInput):
    max_wait_seconds: float | None = Field(default=None, ge=1, le=3600)
