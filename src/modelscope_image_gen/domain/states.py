from enum import StrEnum


class JobStatus(StrEnum):
    SUBMITTING = "submitting"
    SUBMITTED = "submitted"
    IN_PROGRESS = "in_progress"
    SUCCEEDED = "succeeded"
    FAILED = "failed"

    @property
    def is_terminal(self) -> bool:
        return self in {self.SUCCEEDED, self.FAILED}


class ArtifactStatus(StrEnum):
    PENDING = "pending"
    AVAILABLE = "available"
    FAILED = "failed"


class ArtifactAggregateStatus(StrEnum):
    NOT_READY = "not_ready"
    PENDING = "pending"
    PARTIAL = "partial"
    AVAILABLE = "available"
    FAILED = "failed"
