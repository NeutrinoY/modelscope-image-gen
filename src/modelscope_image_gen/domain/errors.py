from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class ErrorStage(StrEnum):
    VALIDATION = "validation"
    CONFIGURATION = "configuration"
    SUBMIT = "submit"
    STATUS_CHECK = "status_check"
    DOWNLOAD = "download"
    ARTIFACT_SAVE = "artifact_save"
    PERSISTENCE = "persistence"
    INTERNAL = "internal"


class ErrorCategory(StrEnum):
    VALIDATION = "validation"
    CONFIGURATION = "configuration"
    NETWORK = "network"
    UPSTREAM_HTTP = "upstream_http"
    UPSTREAM_TASK = "upstream_task"
    UPSTREAM_CONTRACT = "upstream_contract"
    TIMEOUT = "timeout"
    LOCAL_IO = "local_io"
    STATE_CONFLICT = "state_conflict"
    INTERNAL = "internal"


class ErrorCode(StrEnum):
    ARGUMENT_VALIDATION_FAILED = "ARGUMENT_VALIDATION_FAILED"
    MODELSCOPE_TOKEN_MISSING = "MODELSCOPE_TOKEN_MISSING"
    JOB_NOT_FOUND = "JOB_NOT_FOUND"
    INVALID_JOB_STATE = "INVALID_JOB_STATE"
    INVALID_JOB_TRANSITION = "INVALID_JOB_TRANSITION"
    SUBMISSION_REJECTED = "SUBMISSION_REJECTED"
    SUBMISSION_OUTCOME_UNKNOWN = "SUBMISSION_OUTCOME_UNKNOWN"
    NETWORK_ERROR = "NETWORK_ERROR"
    UPSTREAM_HTTP_ERROR = "UPSTREAM_HTTP_ERROR"
    UPSTREAM_RESPONSE_INVALID = "UPSTREAM_RESPONSE_INVALID"
    UPSTREAM_STATUS_UNKNOWN = "UPSTREAM_STATUS_UNKNOWN"
    UPSTREAM_TASK_FAILED = "UPSTREAM_TASK_FAILED"
    EMPTY_OUTPUT_IMAGES = "EMPTY_OUTPUT_IMAGES"
    RESULT_NOT_READY = "RESULT_NOT_READY"
    DOWNLOAD_FAILED = "DOWNLOAD_FAILED"
    DOWNLOAD_TOO_LARGE = "DOWNLOAD_TOO_LARGE"
    IMAGE_TOO_LARGE = "IMAGE_TOO_LARGE"
    IMAGE_VALIDATION_FAILED = "IMAGE_VALIDATION_FAILED"
    ARTIFACT_SAVE_FAILED = "ARTIFACT_SAVE_FAILED"
    PERSISTENCE_ERROR = "PERSISTENCE_ERROR"
    CONCURRENT_MODIFICATION = "CONCURRENT_MODIFICATION"
    INVALID_CURSOR = "INVALID_CURSOR"
    INTERNAL_ERROR = "INTERNAL_ERROR"


@dataclass(frozen=True, slots=True)
class DomainError:
    code: ErrorCode
    stage: ErrorStage
    category: ErrorCategory
    retryable: bool
    safe_message: str
    occurred_at: datetime
    retry_after_seconds: int | None = None
    possibly_submitted: bool = False
    provider_request_id: str | None = None

    def __post_init__(self) -> None:
        if self.retry_after_seconds is not None and self.retry_after_seconds < 0:
            raise ValueError("retry_after_seconds must be non-negative")
        if self.possibly_submitted and self.code is not ErrorCode.SUBMISSION_OUTCOME_UNKNOWN:
            raise ValueError("possibly_submitted is reserved for uncertain submissions")
