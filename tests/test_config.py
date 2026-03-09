# pyright: reportMissingImports=false
import pytest

from modelscope_image_gen.config import Settings


def test_require_api_key_raises_when_missing() -> None:
    settings = Settings(modelscope_sdk_token="")
    with pytest.raises(ValueError, match="MODELSCOPE_SDK_TOKEN"):
        settings.require_api_key()


def test_polling_defaults_reflect_settings() -> None:
    settings = Settings(
        modelscope_sdk_token="token",
        modelscope_poll_interval_seconds=2,
        modelscope_max_poll_attempts=9,
        modelscope_poll_backoff=True,
        modelscope_max_poll_interval_seconds=10,
    )

    defaults = settings.polling_defaults()
    assert defaults["base_interval"] == 2
    assert defaults["max_attempts"] == 9
    assert defaults["backoff"] is True
    assert defaults["max_interval"] == 10
