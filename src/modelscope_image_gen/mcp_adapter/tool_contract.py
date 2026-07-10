from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime

import mcp_types
from pydantic import BaseModel, ValidationError

from modelscope_image_gen.domain import DomainError, ErrorCategory, ErrorCode, ErrorStage
from modelscope_image_gen.mcp_adapter.mapping import error_output
from modelscope_image_gen.mcp_adapter.presenters.common import present


@dataclass(frozen=True, slots=True)
class ToolContract[InputT: BaseModel, OutputT: BaseModel]:
    name: str
    title: str
    description: str
    input_model: type[InputT]
    output_model: type[OutputT]
    annotations: mcp_types.ToolAnnotations
    handler: Callable[[InputT], Awaitable[OutputT]]

    def as_mcp_tool(self) -> mcp_types.Tool:
        return mcp_types.Tool(
            name=self.name,
            title=self.title,
            description=self.description,
            input_schema=self.input_model.model_json_schema(),
            output_schema=self.output_model.model_json_schema(),
            annotations=self.annotations,
            execution=mcp_types.ToolExecution(task_support="forbidden"),
        )

    async def execute(self, arguments: dict | None) -> mcp_types.CallToolResult:
        try:
            input_value = self.input_model.model_validate(arguments or {})
            output = await self.handler(input_value)
        except ValidationError:
            output = self._error_result(
                DomainError(
                    code=ErrorCode.ARGUMENT_VALIDATION_FAILED,
                    stage=ErrorStage.VALIDATION,
                    category=ErrorCategory.VALIDATION,
                    retryable=False,
                    safe_message="The tool arguments did not match the published input schema.",
                    occurred_at=datetime.now(UTC),
                )
            )
        except Exception:
            output = self._error_result(
                DomainError(
                    code=ErrorCode.INTERNAL_ERROR,
                    stage=ErrorStage.INTERNAL,
                    category=ErrorCategory.INTERNAL,
                    retryable=False,
                    safe_message="The server could not complete the operation because of an internal error.",
                    occurred_at=datetime.now(UTC),
                )
            )
        try:
            validated = self.output_model.model_validate(output)
        except ValidationError:
            validated = self._error_result(
                DomainError(
                    code=ErrorCode.INTERNAL_ERROR,
                    stage=ErrorStage.INTERNAL,
                    category=ErrorCategory.INTERNAL,
                    retryable=False,
                    safe_message="The server produced an invalid internal result.",
                    occurred_at=datetime.now(UTC),
                )
            )
        payload = validated.model_dump(mode="json")
        return mcp_types.CallToolResult(
            content=[mcp_types.TextContent(text=present(self.name, validated))],
            structuredContent=payload,
            isError=not payload["ok"],
        )

    def _error_result(self, error: DomainError) -> OutputT:
        return self.output_model.model_validate({"ok": False, "data": None, "error": error_output(error)})
