from io import BytesIO

import pytest
from PIL import Image

from modelscope_image_gen.domain import ImageId, JobId
from modelscope_image_gen.infrastructure.artifacts.store import LocalArtifactStore


def png_bytes() -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (4, 3), "red").save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.mark.anyio
async def test_artifact_store_validates_and_atomically_saves_under_root(tmp_path) -> None:
    reads = 0

    async def chunks():
        nonlocal reads
        reads += 1
        yield png_bytes()

    store = LocalArtifactStore(
        artifact_root=tmp_path / "artifacts",
        max_download_bytes=1024 * 1024,
        max_image_pixels=100,
    )
    job_id = JobId.new()
    image_id = ImageId.new()
    artifact = await store.save(
        job_id=job_id,
        image_id=image_id,
        position=0,
        chunks=chunks(),
        content_length=len(png_bytes()),
    )

    assert reads == 1
    assert artifact.width == 4 and artifact.height == 3
    assert artifact.format == "PNG"
    assert store.resolve_path(artifact).startswith(str((tmp_path / "artifacts").resolve()))
    assert (tmp_path / "artifacts" / artifact.relative_path).read_bytes() == png_bytes()

    (tmp_path / "artifacts" / artifact.relative_path).write_bytes(b"corrupt")
    repaired = await store.save(
        job_id=job_id,
        image_id=image_id,
        position=0,
        chunks=chunks(),
        content_length=len(png_bytes()),
    )

    assert reads == 2
    assert (tmp_path / "artifacts" / repaired.relative_path).read_bytes() == png_bytes()
