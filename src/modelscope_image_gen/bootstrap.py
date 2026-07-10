from __future__ import annotations

import logging
import os
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
from mcp.server.lowlevel import NotificationOptions, Server
from mcp.server.stdio import stdio_server

from modelscope_image_gen.application.use_cases.check_generation import CheckGeneration
from modelscope_image_gen.application.use_cases.fetch_generation_result import FetchGenerationResult
from modelscope_image_gen.application.use_cases.generate_image import GenerateImage
from modelscope_image_gen.application.use_cases.list_generations import ListGenerations
from modelscope_image_gen.application.use_cases.locking import LockedJobUseCase
from modelscope_image_gen.application.use_cases.submit_generation import SubmitGeneration
from modelscope_image_gen.infrastructure.artifacts.maintenance import (
    clean_temporary_files,
    delete_relative_job_directory,
)
from modelscope_image_gen.infrastructure.artifacts.store import LocalArtifactStore
from modelscope_image_gen.infrastructure.concurrency.job_locks import JobLockManager
from modelscope_image_gen.infrastructure.config.logging import configure_logging
from modelscope_image_gen.infrastructure.config.settings import Settings
from modelscope_image_gen.infrastructure.modelscope.provider import ModelScopeProvider
from modelscope_image_gen.infrastructure.sqlite.repository import SqliteGenerationJobRepository
from modelscope_image_gen.infrastructure.system.clock import utc_now
from modelscope_image_gen.infrastructure.system.identifiers import new_image_id, new_job_id
from modelscope_image_gen.infrastructure.system.waiting import wait
from modelscope_image_gen.mcp_adapter.handlers.tools import ToolHandlers
from modelscope_image_gen.mcp_adapter.registry import ToolRegistry
from modelscope_image_gen.mcp_adapter.server import create_server


@dataclass(slots=True)
class Runtime:
    server: Server
    registry: ToolRegistry
    repository: SqliteGenerationJobRepository
    http_client: httpx.AsyncClient
    data_dir: Path
    artifact_root: Path


@asynccontextmanager
async def build_runtime(settings: Settings) -> AsyncIterator[Runtime]:
    data_dir, database_path, artifact_root = settings.resolved_paths()
    data_dir.mkdir(parents=True, exist_ok=True)
    artifact_root.mkdir(parents=True, exist_ok=True)
    if os.name != "nt":
        data_dir.chmod(0o700)
        artifact_root.chmod(0o700)
    repository = await SqliteGenerationJobRepository.open(database_path, artifact_root=artifact_root)
    if os.name != "nt" and database_path.exists():
        database_path.chmod(0o600)
    await repository.recover_stale_submitting()
    clean_temporary_files(artifact_root, retention_hours=settings.temp_file_retention_hours)
    if settings.terminal_job_retention_days > 0:
        cutoff = datetime.now(UTC) - timedelta(days=settings.terminal_job_retention_days)
        await repository.schedule_expired_terminal(cutoff=cutoff)
    for item in await repository.cleanup_items():
        try:
            delete_relative_job_directory(artifact_root, item["relative_job_dir"])
            await repository.complete_cleanup(item["cleanup_id"])
        except Exception as exc:
            logging.getLogger("modelscope-image-gen-mcp").warning(
                "artifact_cleanup_failed cleanup_id=%s", item["cleanup_id"]
            )
            await repository.fail_cleanup(item["cleanup_id"], str(exc))
    client = httpx.AsyncClient(follow_redirects=True)
    try:
        provider = ModelScopeProvider(
            client=client,
            api_base=settings.normalized_api_base,
            token=settings.token_value,
            submit_timeout=settings.submit_timeout_seconds,
            status_timeout=settings.status_timeout_seconds,
        )
        artifacts = LocalArtifactStore(
            client=client,
            artifact_root=artifact_root,
            download_timeout=settings.download_timeout_seconds,
            max_download_bytes=settings.max_download_bytes,
            max_image_pixels=settings.max_image_pixels,
        )
        locks = JobLockManager()
        submit = SubmitGeneration(repository, provider, utc_now, new_job_id)
        check = LockedJobUseCase(CheckGeneration(repository, provider, utc_now, new_image_id), locks)
        fetch = LockedJobUseCase(
            FetchGenerationResult(repository, artifacts, utc_now, settings.max_concurrent_downloads), locks
        )
        list_jobs = ListGenerations(repository, utc_now)
        generate = GenerateImage(
            submit,
            check,
            fetch,
            wait,
            time.monotonic,
            settings.blocking_poll_interval_seconds,
            settings.default_max_wait_seconds,
        )
        handlers = ToolHandlers(
            submit_use_case=submit,
            check_use_case=check,
            fetch_use_case=fetch,
            list_use_case=list_jobs,
            generate_use_case=generate,
            default_model=settings.default_model,
            recommended_wait_seconds=max(1, round(settings.blocking_poll_interval_seconds)),
        )
        registry = ToolRegistry(handlers)
        yield Runtime(create_server(registry), registry, repository, client, data_dir, artifact_root)
    finally:
        await client.aclose()
        await repository.close()


async def serve_stdio() -> None:
    settings = Settings()
    configure_logging(settings.log_level)
    async with build_runtime(settings) as runtime:
        async with stdio_server() as (read_stream, write_stream):
            await runtime.server.run(
                read_stream,
                write_stream,
                runtime.server.create_initialization_options(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            )
