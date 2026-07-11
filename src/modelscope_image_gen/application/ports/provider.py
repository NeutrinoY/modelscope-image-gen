from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager
from typing import Protocol

from modelscope_image_gen.application.provider_outcomes import ProviderCheckOutcome, ProviderSubmitOutcome
from modelscope_image_gen.domain import (
    DomainError,
    GenerationRequest,
    ProviderImageReference,
    ProviderTaskReference,
)


class ProviderImageStream(Protocol):
    content_length: int | None

    def __aiter__(self) -> AsyncIterator[bytes]: ...


class ImageGenerationProvider(Protocol):
    def validate(self, request: GenerationRequest) -> DomainError | None: ...
    async def submit(self, request: GenerationRequest) -> ProviderSubmitOutcome: ...
    async def check(self, task: ProviderTaskReference) -> ProviderCheckOutcome: ...
    def open_image(self, reference: ProviderImageReference) -> AbstractAsyncContextManager[ProviderImageStream]: ...
