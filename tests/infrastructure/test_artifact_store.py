from io import BytesIO

import httpx
import pytest
from PIL import Image

from modelscope_image_gen.domain import ImageId, JobId, ProviderImageReference
from modelscope_image_gen.infrastructure.artifacts.store import LocalArtifactStore


def png_bytes() -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (4, 3), "red").save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.mark.anyio
async def test_artifact_store_validates_and_atomically_saves_under_root(tmp_path) -> None:
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, content=png_bytes(), headers={"Content-Type": "application/octet-stream"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        store = LocalArtifactStore(
            client=client,
            artifact_root=tmp_path / "artifacts",
            download_timeout=2,
            max_download_bytes=1024 * 1024,
            max_image_pixels=100,
        )
        job_id = JobId.new()
        image_id = ImageId.new()
        artifact = await store.materialize(
            job_id=job_id,
            image_id=image_id,
            position=0,
            reference=ProviderImageReference("https://signed/image"),
        )

    assert calls == 1
    assert artifact.width == 4 and artifact.height == 3
    assert artifact.format == "PNG"
    assert artifact.file_path.startswith(str((tmp_path / "artifacts").resolve()))
    assert (tmp_path / "artifacts" / artifact.relative_path).read_bytes() == png_bytes()
