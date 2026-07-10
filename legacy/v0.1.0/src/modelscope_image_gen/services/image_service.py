from __future__ import annotations

from ..config import Settings
from ..infrastructure import ModelScopeClient, TaskStore
from .workflows import (
    ServiceCommonWorkflow,
    ServiceGenerateWorkflow,
    ServicePhaseWorkflow,
    ServiceResultWorkflow,
    ServiceStatusWorkflow,
    ServiceSubmitWorkflow,
)


class ImageGenerationService(
    ServiceSubmitWorkflow,
    ServiceStatusWorkflow,
    ServiceResultWorkflow,
    ServiceGenerateWorkflow,
    ServicePhaseWorkflow,
    ServiceCommonWorkflow,
):
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.task_store = TaskStore(state_dir=settings.modelscope_job_state_dir)
        self.client = ModelScopeClient(
            api_base=settings.modelscope_api_base,
            api_key=settings.modelscope_sdk_token,
            submit_timeout_seconds=settings.modelscope_submit_timeout_seconds,
            poll_timeout_seconds=settings.modelscope_poll_timeout_seconds,
            download_timeout_seconds=settings.modelscope_download_timeout_seconds,
        )
