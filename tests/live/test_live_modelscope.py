from __future__ import annotations

import os

import anyio
import pytest

from modelscope_image_gen.bootstrap import build_runtime
from modelscope_image_gen.infrastructure.config.settings import Settings

pytestmark = pytest.mark.live


@pytest.mark.anyio
async def test_live_modelscope_submit_check_fetch(tmp_path) -> None:
    if os.getenv("MODELSCOPE_IMAGE_GEN_RUN_LIVE_TESTS") != "1" or not os.getenv("MODELSCOPE_SDK_TOKEN"):
        pytest.skip("requires explicit live-test flag and ModelScope token")

    settings = Settings(data_dir=tmp_path)
    async with build_runtime(settings) as runtime:
        submitted = await runtime.registry.call(
            "submit_image_generation",
            {
                "prompt": "A small blue ceramic cup on a plain white table, studio product photograph",
                "size": {"width": 1024, "height": 1024},
            },
        )
        assert submitted.is_error is False
        job_id = submitted.structured_content["data"]["job"]["job_id"]

        for _ in range(120):
            checked = await runtime.registry.call("check_image_generation", {"job_id": job_id})
            status = checked.structured_content["data"]["job"]["status"]
            if status in {"succeeded", "failed"}:
                break
            await anyio.sleep(5)
        assert status == "succeeded"

        fetched = await runtime.registry.call("fetch_image_generation_result", {"job_id": job_id})
        assert fetched.is_error is False
        assert fetched.structured_content["data"]["job"]["available_image_count"] >= 1
