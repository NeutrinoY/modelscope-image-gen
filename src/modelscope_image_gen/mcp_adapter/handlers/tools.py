from __future__ import annotations

from dataclasses import dataclass

from modelscope_image_gen.application.ports.use_cases import CheckUseCase, FetchUseCase
from modelscope_image_gen.application.repositories import JobListQuery
from modelscope_image_gen.application.use_cases.generate_image import GenerateImage
from modelscope_image_gen.application.use_cases.list_generations import ListGenerations
from modelscope_image_gen.application.use_cases.submit_generation import SubmitGeneration
from modelscope_image_gen.domain import GenerationRequest, ImageSize, JobId
from modelscope_image_gen.mcp_adapter.mapping import error_output, image_output, job_output, job_summary, next_action
from modelscope_image_gen.mcp_adapter.models.inputs import (
    CheckImageGenerationInput,
    FetchImageGenerationResultInput,
    GenerateImageInput,
    ListImageGenerationsInput,
    SubmitImageGenerationInput,
)
from modelscope_image_gen.mcp_adapter.models.outputs import (
    CheckData,
    CheckToolOutput,
    FetchData,
    FetchToolOutput,
    GenerateData,
    GenerateToolOutput,
    ListData,
    ListToolOutput,
    SubmitData,
    SubmitToolOutput,
)


@dataclass(frozen=True, slots=True)
class ToolHandlers:
    submit_use_case: SubmitGeneration
    check_use_case: CheckUseCase
    fetch_use_case: FetchUseCase
    list_use_case: ListGenerations
    generate_use_case: GenerateImage
    default_model: str
    recommended_wait_seconds: int

    def _request(self, value: SubmitImageGenerationInput) -> GenerationRequest:
        return GenerationRequest(
            prompt=value.prompt,
            model=value.model or self.default_model,
            size=ImageSize(value.size.width, value.size.height),
            negative_prompt=value.negative_prompt,
            seed=value.seed,
        )

    async def submit(self, value: SubmitImageGenerationInput) -> SubmitToolOutput:
        result = await self.submit_use_case(self._request(value))
        data = (
            SubmitData(job=job_output(result.job, wait_seconds=self.recommended_wait_seconds), accepted=result.accepted)
            if result.job
            else None
        )
        action = next_action(result.job, wait_seconds=self.recommended_wait_seconds) if result.job else None
        return SubmitToolOutput(ok=result.ok, data=data, error=error_output(result.error, action=action))

    async def check(self, value: CheckImageGenerationInput) -> CheckToolOutput:
        try:
            result = await self.check_use_case(JobId(value.job_id))
        except LookupError as exc:
            return CheckToolOutput(ok=False, data=None, error=error_output(exc.args[0]))
        data = CheckData(job=job_output(result.job, wait_seconds=self.recommended_wait_seconds))
        return CheckToolOutput(
            ok=result.ok,
            data=data,
            error=error_output(
                result.error, action=next_action(result.job, wait_seconds=self.recommended_wait_seconds)
            ),
        )

    async def fetch(self, value: FetchImageGenerationResultInput) -> FetchToolOutput:
        try:
            result = await self.fetch_use_case(JobId(value.job_id))
        except LookupError as exc:
            return FetchToolOutput(ok=False, data=None, error=error_output(exc.args[0]))
        data = FetchData(
            job=job_output(result.job, wait_seconds=self.recommended_wait_seconds),
            images=[image_output(image) for image in result.images],
            partial=result.partial,
        )
        return FetchToolOutput(
            ok=result.ok,
            data=data,
            error=error_output(
                result.error, action=next_action(result.job, wait_seconds=self.recommended_wait_seconds)
            ),
        )

    async def list_jobs(self, value: ListImageGenerationsInput) -> ListToolOutput:
        result = await self.list_use_case(
            JobListQuery(
                statuses=tuple(value.statuses) if value.statuses else None, limit=value.limit, cursor=value.cursor
            )
        )
        data = (
            ListData(
                items=[job_summary(job, wait_seconds=self.recommended_wait_seconds) for job in result.items],
                next_cursor=result.next_cursor,
            )
            if result.ok
            else None
        )
        return ListToolOutput(ok=result.ok, data=data, error=error_output(result.error))

    async def generate(self, value: GenerateImageInput) -> GenerateToolOutput:
        result = await self.generate_use_case(self._request(value), max_wait_seconds=value.max_wait_seconds)
        if result.job is None:
            return GenerateToolOutput(ok=False, data=None, error=error_output(result.error))
        data = GenerateData(
            job=job_output(result.job, wait_seconds=self.recommended_wait_seconds),
            images=[image_output(image) for image in result.images],
            completed=result.completed,
            partial=result.partial,
        )
        return GenerateToolOutput(
            ok=result.ok,
            data=data,
            error=error_output(
                result.error, action=next_action(result.job, wait_seconds=self.recommended_wait_seconds)
            ),
        )
