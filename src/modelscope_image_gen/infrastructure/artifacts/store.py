from __future__ import annotations

import hashlib
import os
import secrets
from datetime import UTC, datetime
from pathlib import Path

import httpx
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
    ProviderImageReference,
)

_FORMATS = {
    "PNG": ("png", "image/png"),
    "JPEG": ("jpg", "image/jpeg"),
    "WEBP": ("webp", "image/webp"),
    "GIF": ("gif", "image/gif"),
}


class LocalArtifactStore:
    def __init__(
        self,
        *,
        client: httpx.AsyncClient,
        artifact_root: Path,
        download_timeout: float,
        max_download_bytes: int,
        max_image_pixels: int,
    ) -> None:
        self._client = client
        self._root = artifact_root.resolve()
        self._download_timeout = download_timeout
        self._max_download_bytes = max_download_bytes
        self._max_image_pixels = max_image_pixels
        self._root.mkdir(parents=True, exist_ok=True)

    async def materialize(
        self,
        *,
        job_id: JobId,
        image_id: ImageId,
        position: int,
        reference: ProviderImageReference,
    ) -> LocalArtifact:
        job_dir = self._safe_join("jobs", str(job_id))
        temp_dir = self._safe_join("jobs", str(job_id), ".tmp")
        job_dir.mkdir(parents=True, exist_ok=True)
        temp_dir.mkdir(parents=True, exist_ok=True)
        existing = self._inspect_existing(job_id=job_id, image_id=image_id, position=position)
        if existing is not None:
            return existing
        temp_path = self._safe_join("jobs", str(job_id), ".tmp", f"{secrets.token_hex(12)}.part")
        digest = hashlib.sha256()
        byte_size = 0
        try:
            async with self._client.stream("GET", reference.locator, timeout=self._download_timeout) as response:
                response.raise_for_status()
                length = response.headers.get("Content-Length")
                if length and int(length) > self._max_download_bytes:
                    raise self._error(
                        ErrorCode.DOWNLOAD_TOO_LARGE, "The image download exceeds the configured byte limit."
                    )
                with temp_path.open("xb") as output:
                    async for chunk in response.aiter_bytes():
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
            if final_path.exists():
                final_path.unlink()
            os.replace(temp_path, final_path)
            return LocalArtifact(
                artifact_key=ArtifactKey(f"jobs/{job_id}/images/{image_id}"),
                file_path=str(final_path),
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
        except httpx.HTTPStatusError as exc:
            raise self._error(
                ErrorCode.DOWNLOAD_FAILED,
                "The image artifact could not be downloaded from ModelScope.",
                retryable=exc.response.status_code in {408, 409, 425, 429, 500, 502, 503, 504},
                provider_request_id=exc.response.headers.get("X-Request-Id"),
            ) from exc
        except httpx.RequestError as exc:
            raise self._error(
                ErrorCode.DOWNLOAD_FAILED,
                "The image artifact could not be downloaded because of a network error.",
                retryable=True,
            ) from exc
        except (OSError, ValueError) as exc:
            raise self._error(
                ErrorCode.ARTIFACT_SAVE_FAILED, "The image artifact could not be safely stored on this machine."
            ) from exc
        finally:
            if temp_path.exists():
                temp_path.unlink(missing_ok=True)

    def _inspect_existing(self, *, job_id: JobId, image_id: ImageId, position: int) -> LocalArtifact | None:
        for format_name, (extension, media_type) in _FORMATS.items():
            relative_path = f"jobs/{job_id}/{position:03d}-{image_id}.{extension}"
            path = self._safe_join(*relative_path.split("/"))
            if not path.is_file():
                continue
            actual_format, width, height = self._validate_image(path)
            if actual_format != format_name:
                continue
            content = path.read_bytes()
            return LocalArtifact(
                artifact_key=ArtifactKey(f"jobs/{job_id}/images/{image_id}"),
                file_path=str(path),
                relative_path=relative_path,
                sha256=hashlib.sha256(content).hexdigest(),
                byte_size=len(content),
                media_type=media_type,
                format=actual_format,
                width=width,
                height=height,
                saved_at=datetime.fromtimestamp(path.stat().st_mtime, UTC),
            )
        return None

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
        candidate = self._root.joinpath(*components).resolve()
        if not candidate.is_relative_to(self._root):
            raise ValueError("artifact path escapes configured root")
        current = self._root
        for component in components[:-1]:
            current = current / component
            if current.exists() and current.is_symlink():
                raise ValueError("artifact path contains a symbolic link")
        return candidate

    def _error(
        self,
        code: ErrorCode,
        message: str,
        *,
        retryable: bool = False,
        provider_request_id: str | None = None,
    ) -> ArtifactMaterializationError:
        category = ErrorCategory.NETWORK if retryable else ErrorCategory.LOCAL_IO
        stage = (
            ErrorStage.DOWNLOAD
            if code in {ErrorCode.DOWNLOAD_FAILED, ErrorCode.DOWNLOAD_TOO_LARGE}
            else ErrorStage.ARTIFACT_SAVE
        )
        return ArtifactMaterializationError(
            DomainError(
                code=code,
                stage=stage,
                category=category,
                retryable=retryable,
                retry_after_seconds=1 if retryable else None,
                safe_message=message,
                occurred_at=datetime.now(UTC),
                provider_request_id=provider_request_id,
            )
        )
