from __future__ import annotations

from modelscope_image_gen.application.ports.system import Clock
from modelscope_image_gen.application.repositories import GenerationJobRepository, JobListQuery
from modelscope_image_gen.application.results import ListResult
from modelscope_image_gen.domain import DomainError, ErrorCategory, ErrorCode, ErrorStage


class ListGenerations:
    def __init__(self, repository: GenerationJobRepository, clock: Clock) -> None:
        self._repository = repository
        self._clock = clock

    async def __call__(self, query: JobListQuery) -> ListResult:
        try:
            page = await self._repository.list(query)
        except ValueError as exc:
            if str(exc) != "INVALID_CURSOR":
                raise
            error = DomainError(
                code=ErrorCode.INVALID_CURSOR,
                stage=ErrorStage.VALIDATION,
                category=ErrorCategory.VALIDATION,
                retryable=False,
                safe_message="The pagination cursor is invalid or does not match the requested filters.",
                occurred_at=self._clock(),
            )
            return ListResult(ok=False, items=(), next_cursor=None, error=error)
        return ListResult(ok=True, items=page.items, next_cursor=page.next_cursor)
