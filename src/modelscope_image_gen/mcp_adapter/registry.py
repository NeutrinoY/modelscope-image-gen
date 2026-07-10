from __future__ import annotations

import mcp_types

from modelscope_image_gen.mcp_adapter.handlers.tools import ToolHandlers
from modelscope_image_gen.mcp_adapter.models.inputs import (
    CheckImageGenerationInput,
    FetchImageGenerationResultInput,
    GenerateImageInput,
    ListImageGenerationsInput,
    SubmitImageGenerationInput,
)
from modelscope_image_gen.mcp_adapter.models.outputs import (
    CheckToolOutput,
    FetchToolOutput,
    GenerateToolOutput,
    ListToolOutput,
    SubmitToolOutput,
)
from modelscope_image_gen.mcp_adapter.tool_contract import ToolContract


class ToolRegistry:
    def __init__(self, handlers: ToolHandlers) -> None:
        self._contracts = (
            ToolContract(
                name="submit_image_generation",
                title="Submit Image Generation",
                description=(
                    "Create a new asynchronous ModelScope text-to-image job. "
                    "This accesses an external service and may consume quota. "
                    "It returns a local job ID without waiting for images. "
                    "Scheduled agents should start here and normally call check_image_generation next. "
                    "Repeated calls may create duplicate external jobs."
                ),
                input_model=SubmitImageGenerationInput,
                output_model=SubmitToolOutput,
                annotations=mcp_types.ToolAnnotations(
                    readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=True
                ),
                handler=handlers.submit,
            ),
            ToolContract(
                name="check_image_generation",
                title="Check Image Generation",
                description=(
                    "Refresh one submitted or in-progress job with at most one ModelScope status request. "
                    "This updates local state but does not create a task or download images. "
                    "Terminal jobs are returned from local storage. "
                    "Successful jobs normally continue with fetch_image_generation_result."
                ),
                input_model=CheckImageGenerationInput,
                output_model=CheckToolOutput,
                annotations=mcp_types.ToolAnnotations(
                    readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=True
                ),
                handler=handlers.check,
            ),
            ToolContract(
                name="fetch_image_generation_result",
                title="Fetch Image Generation Result",
                description=(
                    "For a succeeded job, download, validate, and safely save images that are not yet available. This "
                    "accesses the network and writes local files. Available images are not downloaded or overwritten "
                    "again; partial failures can be retried."
                ),
                input_model=FetchImageGenerationResultInput,
                output_model=FetchToolOutput,
                annotations=mcp_types.ToolAnnotations(
                    readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=True
                ),
                handler=handlers.fetch,
            ),
            ToolContract(
                name="list_image_generations",
                title="List Image Generations",
                description=(
                    "Read local SQLite job summaries to recover lost job IDs. "
                    "This does not access ModelScope or refresh status. "
                    "It does not return prompts, provider locators, or artifact paths. "
                    "It supports status filters and opaque cursor pagination."
                ),
                input_model=ListImageGenerationsInput,
                output_model=ListToolOutput,
                annotations=mcp_types.ToolAnnotations(
                    readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False
                ),
                handler=handlers.list_jobs,
            ),
            ToolContract(
                name="generate_image",
                title="Generate Image",
                description=(
                    "Blocking convenience orchestration over submit, check, and fetch. "
                    "It accesses ModelScope, may consume quota, waits, and writes local files. "
                    "Scheduled agents should prefer the asynchronous tools. "
                    "At the local wait limit it returns the job ID for asynchronous continuation. "
                    "Timeout or cancellation does not cancel the upstream job."
                ),
                input_model=GenerateImageInput,
                output_model=GenerateToolOutput,
                annotations=mcp_types.ToolAnnotations(
                    readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=True
                ),
                handler=handlers.generate,
            ),
        )
        self._by_name = {contract.name: contract for contract in self._contracts}

    def tools(self) -> list[mcp_types.Tool]:
        return [contract.as_mcp_tool() for contract in self._contracts]

    async def call(self, name: str, arguments: dict | None) -> mcp_types.CallToolResult:
        contract = self._by_name.get(name)
        if contract is None:
            raise KeyError(name)
        return await contract.execute(arguments)
