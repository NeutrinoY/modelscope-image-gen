from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from .paths import resolve_data_paths


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="MODELSCOPE_IMAGE_GEN_",
        env_file=(".env", ".env.local"),
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    api_base: str = "https://api-inference.modelscope.cn/"
    default_model: str = "krea/Krea-2-Turbo"
    log_level: str = "INFO"
    data_dir: Path | None = None
    database_path: Path | None = None
    artifact_root: Path | None = None
    submit_timeout_seconds: float = Field(default=30, gt=0)
    status_timeout_seconds: float = Field(default=30, gt=0)
    download_timeout_seconds: float = Field(default=60, gt=0)
    blocking_poll_interval_seconds: float = Field(default=5, gt=0)
    default_max_wait_seconds: float = Field(default=600, gt=0)
    max_concurrent_downloads: int = Field(default=4, ge=1)
    max_download_bytes: int = Field(default=52_428_800, gt=0)
    max_image_pixels: int = Field(default=40_000_000, gt=0)
    terminal_job_retention_days: int = Field(default=0, ge=0)
    temp_file_retention_hours: int = Field(default=24, ge=0)
    modelscope_sdk_token: SecretStr = Field(default=SecretStr(""), validation_alias="MODELSCOPE_SDK_TOKEN")

    @field_validator("default_model")
    @classmethod
    def validate_model(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("default model must not be empty")
        return value

    @field_validator("api_base")
    @classmethod
    def validate_api_base(cls, value: str) -> str:
        value = value.strip().rstrip("/") + "/"
        if urlparse(value).scheme != "https":
            raise ValueError("ModelScope API base must use HTTPS")
        return value

    @model_validator(mode="after")
    def validate_paths(self) -> Settings:
        data_dir, database_path, artifact_root = self.resolved_paths()
        if data_dir.exists() and not data_dir.is_dir():
            raise ValueError("data directory points to a file")
        if artifact_root.exists() and not artifact_root.is_dir():
            raise ValueError("artifact root points to a file")
        if database_path.exists() and database_path.is_dir():
            raise ValueError("database path points to a directory")
        for path in (data_dir, database_path, artifact_root):
            if "legacy" in {part.lower() for part in path.parts}:
                raise ValueError("runtime data must not be stored inside legacy")
        return self

    @property
    def normalized_api_base(self) -> str:
        return self.api_base

    @property
    def token_value(self) -> str:
        return self.modelscope_sdk_token.get_secret_value()

    def resolved_paths(self) -> tuple[Path, Path, Path]:
        return resolve_data_paths(
            data_dir=self.data_dir, database_path=self.database_path, artifact_root=self.artifact_root
        )
