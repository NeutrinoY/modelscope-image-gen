from __future__ import annotations

from dataclasses import dataclass

from modelscope_image_gen.domain import DomainError, ProviderImageReference


@dataclass(frozen=True, slots=True)
class SubmitAccepted:
    task_id: str
    provider_request_id: str | None
    provider_status: str | None


@dataclass(frozen=True, slots=True)
class SubmitRejected:
    error: DomainError


@dataclass(frozen=True, slots=True)
class SubmitUnknown:
    error: DomainError


ProviderSubmitOutcome = SubmitAccepted | SubmitRejected | SubmitUnknown


@dataclass(frozen=True, slots=True)
class ProviderPending:
    provider_request_id: str | None
    provider_status: str


@dataclass(frozen=True, slots=True)
class ProviderRunning:
    provider_request_id: str | None
    provider_status: str


@dataclass(frozen=True, slots=True)
class ProviderSucceeded:
    references: tuple[ProviderImageReference, ...]
    provider_request_id: str | None
    provider_status: str


@dataclass(frozen=True, slots=True)
class ProviderFailed:
    error: DomainError
    provider_request_id: str | None
    provider_status: str


@dataclass(frozen=True, slots=True)
class ProviderUnknownStatus:
    error: DomainError
    provider_request_id: str | None
    provider_status: str


ProviderCheckOutcome = ProviderPending | ProviderRunning | ProviderSucceeded | ProviderFailed | ProviderUnknownStatus


class ProviderTemporaryError(Exception):
    def __init__(self, error: DomainError) -> None:
        super().__init__(error.safe_message)
        self.error = error


class ProviderImageError(Exception):
    def __init__(self, error: DomainError) -> None:
        super().__init__(error.safe_message)
        self.error = error
