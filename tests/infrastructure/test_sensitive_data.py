import httpx
import pytest

from modelscope_image_gen.application.provider_outcomes import SubmitRejected
from modelscope_image_gen.domain import GenerationRequest
from modelscope_image_gen.infrastructure.config.settings import Settings
from modelscope_image_gen.infrastructure.modelscope.provider import ModelScopeProvider


@pytest.mark.anyio
async def test_upstream_body_and_token_are_not_returned_or_represented() -> None:
    sentinel = "sentinel-secret-token-9dcf0a"

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text=f'{{"token":"{sentinel}"}}')

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = ModelScopeProvider(
            client=client,
            api_base="https://api.example/",
            token=sentinel,
            submit_timeout=2,
            status_timeout=2,
        )
        outcome = await provider.submit(GenerationRequest(prompt="cat", model="m"))

    assert isinstance(outcome, SubmitRejected)
    assert sentinel not in repr(outcome)
    assert sentinel not in repr(Settings(modelscope_sdk_token=sentinel))


def test_default_logging_suppresses_http_request_urls() -> None:
    import logging

    from modelscope_image_gen.infrastructure.config.logging import configure_logging

    configure_logging("INFO")
    assert logging.getLogger("httpx").getEffectiveLevel() >= logging.WARNING
    assert logging.getLogger("httpcore").getEffectiveLevel() >= logging.WARNING
