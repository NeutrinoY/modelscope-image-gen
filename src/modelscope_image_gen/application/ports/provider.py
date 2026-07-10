from __future__ import annotations

from typing import Protocol

from modelscope_image_gen.application.provider_outcomes import ProviderCheckOutcome, ProviderSubmitOutcome
from modelscope_image_gen.domain import DomainError, GenerationRequest, ProviderTaskReference


class ImageGenerationProvider(Protocol):
    def validate(self, request: GenerationRequest) -> DomainError | None: ...
    async def submit(self, request: GenerationRequest) -> ProviderSubmitOutcome: ...
    async def check(self, task: ProviderTaskReference) -> ProviderCheckOutcome: ...
