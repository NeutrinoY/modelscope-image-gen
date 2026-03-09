from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    modelscope_sdk_token: str = Field(default="", validation_alias="MODELSCOPE_SDK_TOKEN")
    modelscope_api_base: str = Field(default="https://api-inference.modelscope.cn/")
    default_model: str = Field(default="Qwen/Qwen-Image")
    modelscope_log_level: str = Field(default="INFO", validation_alias="MODELSCOPE_LOG_LEVEL")

    modelscope_poll_interval_seconds: float = Field(default=5, validation_alias="MODELSCOPE_POLL_INTERVAL_SECONDS")
    modelscope_max_poll_attempts: int = Field(default=120, validation_alias="MODELSCOPE_MAX_POLL_ATTEMPTS")
    modelscope_poll_backoff: bool = Field(default=False, validation_alias="MODELSCOPE_POLL_BACKOFF")
    modelscope_max_poll_interval_seconds: float = Field(
        default=30,
        validation_alias="MODELSCOPE_MAX_POLL_INTERVAL_SECONDS",
    )

    def polling_defaults(self) -> dict[str, float | int | bool]:
        return {
            "base_interval": self.modelscope_poll_interval_seconds,
            "max_attempts": self.modelscope_max_poll_attempts,
            "backoff": self.modelscope_poll_backoff,
            "max_interval": self.modelscope_max_poll_interval_seconds,
        }

    def require_api_key(self) -> str:
        if not self.modelscope_sdk_token:
            raise ValueError("需要设置 MODELSCOPE_SDK_TOKEN 环境变量")
        return self.modelscope_sdk_token


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
