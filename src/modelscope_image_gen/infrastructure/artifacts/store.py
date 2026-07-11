from __future__ import annotations

import hashlib
import logging
import os
import secrets
from collections.abc import AsyncIterable
from datetime import UTC, datetime
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from modelscope_image_gen.application.ports.artifact_store import ArtifactMaterializationError
from modelscope_image_gen.domain import (
    ArtifactKey,
    DomainError,
    ErrorCategory,
    ErrorCode,
    ErrorStage,
    ImageId,
    JobId,
    LocalArtifact,
)

_FORMATS = {
    "PNG": ("png", "image/png"),
    "JPEG": ("jpg", "image/jpeg"),
    "WEBP": ("webp", "image/webp"),
    "GIF": ("gif", "image/gif"),
}
logger = logging.getLogger("modelscope-image-gen-mcp")


class LocalArtifactStore:
    def __init__(
        self,
        *,
        artifact_root: Path,
        max_download_bytes: int,
        max_image_pixels: int,
    ) -> None:
        self._root = artifact_root.resolve()
        self._max_download_bytes = max_download_bytes
        self._max_image_pixels = max_image_pixels
        self._root.mkdir(parents=True, exist_ok=True)

    async def save(
        self,
        *,
        job_id: JobId,
        image_id: ImageId,
        position: int,
        chunks: AsyncIterable[bytes],
        content_length: int | None,
    ) -> LocalArtifact:
        job_dir = self._safe_join("jobs", str(job_id))
        temp_dir = self._safe_join("jobs", str(job_id), ".tmp")
        job_dir.mkdir(parents=True, exist_ok=True)
        temp_dir.mkdir(parents=True, exist_ok=True)
        existing = self.inspect_existing(job_id=job_id, image_id=image_id, position=position)
        if existing is not None:
            return existing
        temp_path = self._safe_join("jobs", str(job_id), ".tmp", f"{secrets.token_hex(12)}.part")
        digest = hashlib.sha256()
        byte_size = 0
        try:
            if content_length is not None and content_length > self._max_download_bytes:
                raise self._error(ErrorCode.DOWNLOAD_TOO_LARGE, "The image download exceeds the configured byte limit.")
            with temp_path.open("xb") as output:
                async for chunk in chunks:
                    byte_size += len(chunk)
                    if byte_size > self._max_download_bytes:
                        raise self._error(
                            ErrorCode.DOWNLOAD_TOO_LARGE, "The image download exceeds the configured byte limit."
                        )
                    digest.update(chunk)
                    output.write(chunk)
                output.flush()
                os.fsync(output.fileno())
            format_name, width, height = self._validate_image(temp_path)
            extension, media_type = _FORMATS[format_name]
            relative_path = f"jobs/{job_id}/{position:03d}-{image_id}.{extension}"
            final_path = self._safe_join(*relative_path.split("/"))
            # Revalidate immediately before the atomic commit to narrow path-swap races.
            if self._safe_join(*relative_path.split("/")) != final_path:
                raise ValueError("artifact path changed before commit")
            os.replace(temp_path, final_path)
            return LocalArtifact(
                artifact_key=ArtifactKey(f"jobs/{job_id}/images/{image_id}"),
                relative_path=relative_path,
                sha256=digest.hexdigest(),
                byte_size=byte_size,
                media_type=media_type,
                format=format_name,
                width=width,
                height=height,
                saved_at=datetime.now(UTC),
            )
        except ArtifactMaterializationError:
            raise
        except (OSError, ValueError) as exc:
            raise self._error(
                ErrorCode.ARTIFACT_SAVE_FAILED, "The image artifact could not be safely stored on this machine."
            ) from exc
        finally:
            try:
                if temp_path.exists():
                    temp_path.unlink(missing_ok=True)
            except OSError:
                logger.warning("artifact.temp_cleanup_failed job_id=%s image_id=%s", job_id, image_id)

    def inspect_existing(self, *, job_id: JobId, image_id: ImageId, position: int) -> LocalArtifact | None:
        for format_name, (extension, media_type) in _FORMATS.items():
            relative_path = f"jobs/{job_id}/{position:03d}-{image_id}.{extension}"
            path = self._safe_join(*relative_path.split("/"))
            if not path.is_file():
                continue
            try:
                actual_format, width, height = self._validate_image(path)
            except ArtifactMaterializationError:
                continue
            if actual_format != format_name:
                continue
            byte_size = path.stat().st_size
            if byte_size <= 0 or byte_size > self._max_download_bytes:
                continue
            digest = hashlib.sha256()
            with path.open("rb") as existing_file:
                for chunk in iter(lambda: existing_file.read(1024 * 1024), b""):
                    digest.update(chunk)
            return LocalArtifact(
                artifact_key=ArtifactKey(f"jobs/{job_id}/images/{image_id}"),
                relative_path=relative_path,
                sha256=digest.hexdigest(),
                byte_size=byte_size,
                media_type=media_type,
                format=actual_format,
                width=width,
                height=height,
                saved_at=datetime.fromtimestamp(path.stat().st_mtime, UTC),
            )
        return None

    def resolve_path(self, artifact: LocalArtifact) -> str:
        return str(self._safe_join(*artifact.relative_path.split("/")))

    def _validate_image(self, path: Path) -> tuple[str, int, int]:
        try:
            with Image.open(path) as image:
                format_name = str(image.format or "").upper()
                width, height = image.size
                if format_name not in _FORMATS:
                    raise self._error(
                        ErrorCode.IMAGE_VALIDATION_FAILED, "The downloaded image format is not supported."
                    )
                if width <= 0 or height <= 0 or width * height > self._max_image_pixels:
                    raise self._error(
                        ErrorCode.IMAGE_TOO_LARGE, "The downloaded image exceeds the configured pixel limit."
                    )
                image.verify()
            return format_name, width, height
        except ArtifactMaterializationError:
            raise
        except (UnidentifiedImageError, OSError, ValueError) as exc:
            raise self._error(
                ErrorCode.IMAGE_VALIDATION_FAILED, "The downloaded bytes are not a valid supported image."
            ) from exc

    def _safe_join(self, *components: str) -> Path:
        if any(not value or value in {".", ".."} or "/" in value or "\\" in value for value in components):
            raise ValueError("unsafe artifact path component")
        current = self._root
        for component in components:
            current = current / component
            if current.exists() and (current.is_symlink() or current.is_junction()):
                raise ValueError("artifact path contains a link or reparse point")
        candidate = current.resolve()
        if not candidate.is_relative_to(self._root):
            raise ValueError("artifact path escapes configured root")
        return candidate

    def _error(
        self,
        code: ErrorCode,
        message: str,
    ) -> ArtifactMaterializationError:
        stage = (
            ErrorStage.DOWNLOAD
            if code in {ErrorCode.DOWNLOAD_FAILED, ErrorCode.DOWNLOAD_TOO_LARGE}
            else ErrorStage.ARTIFACT_SAVE
        )
        return ArtifactMaterializationError(
            DomainError(
                code=code,
                stage=stage,
                category=ErrorCategory.LOCAL_IO,
                retryable=False,
                safe_message=message,
                occurred_at=datetime.now(UTC),
            )
        )
