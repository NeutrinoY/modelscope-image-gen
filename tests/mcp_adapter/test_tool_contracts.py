from datetime import UTC, datetime

import mcp_types
import pytest
from pydantic import ValidationError

from modelscope_image_gen.application.repositories import RepositoryError
from modelscope_image_gen.bootstrap import build_runtime
from modelscope_image_gen.domain import DomainError, ErrorCategory, ErrorCode, ErrorStage
from modelscope_image_gen.infrastructure.config.settings import Settings
from modelscope_image_gen.mcp_adapter.models.inputs import ListImageGenerationsInput
from modelscope_image_gen.mcp_adapter.models.outputs import ListToolOutput
from modelscope_image_gen.mcp_adapter.tool_contract import ToolContract


@pytest.mark.anyio
async def test_registry_has_fixed_five_tool_order_and_generated_schemas(tmp_path) -> None:
    settings = Settings(data_dir=tmp_path, modelscope_sdk_token="")
    async with build_runtime(settings) as runtime:
        tools = runtime.registry.tools()
        assert [tool.name for tool in tools] == [
            "submit_image_generation",
            "check_image_generation",
            "fetch_image_generation_result",
            "list_image_generations",
            "generate_image",
        ]
        submit_schema = tools[0].input_schema
        assert "output_dir" not in submit_schema["properties"]
        assert "output_filename" not in submit_schema["properties"]
        assert tools[0].annotations.idempotent_hint is False
        assert tools[3].annotations.read_only_hint is True


@pytest.mark.anyio
async def test_known_tool_validation_error_uses_structured_envelope(tmp_path) -> None:
    settings = Settings(data_dir=tmp_path, modelscope_sdk_token="")
    async with build_runtime(settings) as runtime:
        result = await runtime.registry.call("submit_image_generation", {})

    assert result.is_error is True
    assert result.structured_content["ok"] is False
    assert result.structured_content["error"]["code"] == "ARGUMENT_VALIDATION_FAILED"
    assert len(result.content) == 1
    assert "JSON:" not in result.content[0].text


@pytest.mark.anyio
async def test_list_is_available_without_modelscope_token(tmp_path) -> None:
    settings = Settings(data_dir=tmp_path, modelscope_sdk_token="")
    async with build_runtime(settings) as runtime:
        result = await runtime.registry.call("list_image_generations", {})

    assert result.is_error is False
    assert result.structured_content["data"]["items"] == []


@pytest.mark.anyio
async def test_submit_without_token_fails_before_job_creation(tmp_path) -> None:
    settings = Settings(data_dir=tmp_path, modelscope_sdk_token="")
    async with build_runtime(settings) as runtime:
        result = await runtime.registry.call("submit_image_generation", {"prompt": "cat"})
        listing = await runtime.registry.call("list_image_generations", {})

    assert result.is_error is True
    assert result.structured_content["error"]["code"] == "MODELSCOPE_TOKEN_MISSING"
    assert result.structured_content["data"] is None
    assert listing.structured_content["data"]["items"] == []


def test_tool_envelope_rejects_inconsistent_success_shape() -> None:
    with pytest.raises(ValidationError):
        ListToolOutput(ok=True, data=None, error=None)


@pytest.mark.anyio
async def test_repository_failure_keeps_stable_reason_code_at_tool_boundary() -> None:
    error = DomainError(
        code=ErrorCode.PERSISTENCE_ERROR,
        stage=ErrorStage.PERSISTENCE,
        category=ErrorCategory.LOCAL_IO,
        retryable=True,
        safe_message="The local image generation state could not be read or saved.",
        occurred_at=datetime.now(UTC),
    )

    async def fail(_value: ListImageGenerationsInput) -> ListToolOutput:
        raise RepositoryError(error)

    contract = ToolContract(
        name="list_image_generations",
        title="List Image Generations",
        description="test",
        input_model=ListImageGenerationsInput,
        output_model=ListToolOutput,
        annotations=mcp_types.ToolAnnotations(),
        handler=fail,
    )
    result = await contract.execute({})

    assert result.is_error is True
    assert result.structured_content["error"]["code"] == "PERSISTENCE_ERROR"
