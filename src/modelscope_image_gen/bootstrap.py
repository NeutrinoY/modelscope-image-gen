from __future__ import annotations

import logging
import os
import time
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager
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

logger = logging.getLogger("modelscope-image-gen-mcp")


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
    async with AsyncExitStack() as stack:
        client = await stack.enter_async_context(httpx.AsyncClient(follow_redirects=True))
        repository = await SqliteGenerationJobRepository.open(database_path)
        stack.push_async_callback(repository.close)
        logger.info("database.opened")
        if os.name != "nt" and database_path.exists():
            database_path.chmod(0o600)
        recovered = await repository.recover_stale_submitting()
        if recovered:
            logger.warning("recovery.submitting_marked_uncertain count=%d", recovered)
        removed_temp_files = clean_temporary_files(artifact_root, retention_hours=settings.temp_file_retention_hours)
        logger.info("maintenance.temp_cleanup_completed count=%d", removed_temp_files)
        if settings.terminal_job_retention_days > 0:
            cutoff = datetime.now(UTC) - timedelta(days=settings.terminal_job_retention_days)
            scheduled = await repository.schedule_expired_terminal(cutoff=cutoff)
            logger.info("maintenance.retention_completed count=%d", scheduled)
        cleanup_count = 0
        for item in await repository.cleanup_items():
            try:
                delete_relative_job_directory(artifact_root, item["relative_job_dir"])
                await repository.complete_cleanup(item["cleanup_id"])
                cleanup_count += 1
            except Exception:
                logger.warning("maintenance.artifact_cleanup_failed cleanup_id=%s", item["cleanup_id"])
                await repository.fail_cleanup(item["cleanup_id"], "Artifact directory cleanup failed.")
        if cleanup_count:
            logger.info("maintenance.artifact_cleanup_completed count=%d", cleanup_count)
        provider = ModelScopeProvider(
            client=client,
            api_base=settings.normalized_api_base,
            token=settings.token_value,
            submit_timeout=settings.submit_timeout_seconds,
            status_timeout=settings.status_timeout_seconds,
            download_timeout=settings.download_timeout_seconds,
        )
        artifacts = LocalArtifactStore(
            artifact_root=artifact_root,
            max_download_bytes=settings.max_download_bytes,
            max_image_pixels=settings.max_image_pixels,
        )
        locks = JobLockManager()
        submit = SubmitGeneration(repository, provider, utc_now, new_job_id)
        check = LockedJobUseCase(CheckGeneration(repository, provider, utc_now, new_image_id), locks)
        fetch = LockedJobUseCase(
            FetchGenerationResult(repository, provider, artifacts, utc_now, settings.max_concurrent_downloads), locks
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


async def serve_stdio() -> None:
    settings = Settings()
    configure_logging(settings.log_level)
    logger.info("server.starting")
    ready = False
    try:
        async with build_runtime(settings) as runtime:
            ready = True
            logger.info("server.ready")
            try:
                async with stdio_server() as (read_stream, write_stream):
                    await runtime.server.run(
                        read_stream,
                        write_stream,
                        runtime.server.create_initialization_options(
                            notification_options=NotificationOptions(),
                            experimental_capabilities={},
                        ),
                    )
            finally:
                logger.info("server.stopping")
    except BaseException:
        if not ready:
            logger.error("server.startup_failed")
        raise
    finally:
        if ready:
            logger.info("server.stopped")
