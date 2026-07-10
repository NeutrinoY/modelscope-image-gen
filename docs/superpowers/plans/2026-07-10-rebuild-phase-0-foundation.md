# ModelScope Image Gen MCP Rebuild Phase 0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve the approved minimum legacy evidence, then establish a clean Python 3.14, uv-managed, MCP v2 project foundation that imports safely, starts a tools-only stdio server, passes quality gates, and builds an installable wheel.

**Architecture:** The archived v0.1.0 files are read-only evidence outside the root project. The new root uses a src-layout package with a lightweight CLI, dependency-free import surface, Pydantic settings and platformdirs path resolution in infrastructure, and a low-level MCP v2 Server exposing an empty tools list until the submit vertical slice is implemented.

**Tech Stack:** Python >=3.14,<3.15; uv/uv_build >=0.11.28,<0.12; mcp==2.0.0b1 with prerelease resolution enabled; AnyIO; Pydantic 2.13; pydantic-settings 2.14; platformdirs 4; Ruff 0.14; ty 0.0.58; pytest 9.

## Global Constraints

- Work on branch `rebuild/v0.2.0`; preserve commit `42c0709` with annotated tag `legacy/v0.1.0`.
- Archive only the exact minimum manifest from `docs/rebuild/08-implementation-brief.md`; the Git tag is the complete old-project snapshot.
- Do not move, delete, or commit `.venv/`, `.ruff_cache/`, `outputs/`, `.env`, generated images, or runtime Job data.
- New code must not import `legacy/` and legacy must be excluded from build, test, Ruff, and ty discovery.
- Package imports must not parse settings, create directories, open databases, create HTTP clients, or configure logging.
- stdout is reserved for MCP wire traffic or explicit CLI output such as `--version`; logs go to stderr.
- Do not register unfinished tool placeholders. Phase 0 advertises Tools capability with an empty list.
- Use exact MCP beta and ty pins; dependency upgrades are separate changes.
- Every task ends with its focused verification and an intentional commit.

---

### Task 1: Preserve the approved design and source-control baseline

**Files:**
- Commit: `docs/rebuild/00-rebuild-direction.md` through `docs/rebuild/08-implementation-brief.md`
- Commit: `docs/superpowers/plans/2026-07-10-rebuild-phase-0-foundation.md`

**Interfaces:**
- Consumes: current `main` commit `42c0709` and the approved 00–08 contracts.
- Produces: annotated tag `legacy/v0.1.0`, branch `rebuild/v0.2.0`, and a committed design baseline.

- [ ] **Step 1: Verify the old baseline before changing Git state**

Run:

```powershell
git branch --show-current
git rev-parse HEAD
git status --short
uv run pytest -q
uv run ruff check
```

Expected: branch `main`, HEAD `42c0709...`, only `docs/` is untracked/modified for this rebuild, `28 passed`, and Ruff reports success.

- [ ] **Step 2: Verify the reserved tag and branch do not already exist**

Run:

```powershell
git show-ref --verify --quiet refs/tags/legacy/v0.1.0; $LASTEXITCODE
git show-ref --verify --quiet refs/heads/rebuild/v0.2.0; $LASTEXITCODE
```

Expected: both commands return exit code `1`. If either exists, inspect it and stop instead of overwriting it.

- [ ] **Step 3: Create the immutable old-code tag and rebuild branch**

Run:

```powershell
git tag -a legacy/v0.1.0 42c0709 -m "Archive modelscope-image-gen-mcp v0.1.0 baseline"
git switch -c rebuild/v0.2.0
```

Expected: current branch is `rebuild/v0.2.0`; the tag resolves to `42c0709`.

- [ ] **Step 4: Commit the approved design and Phase 0 plan**

Run:

```powershell
git add docs/rebuild docs/superpowers/plans/2026-07-10-rebuild-phase-0-foundation.md
git diff --cached --check
git commit -m "docs: define rebuild contract"
```

Expected: one documentation-only commit; no runtime file is changed.

### Task 2: Create the minimum semantic legacy archive

**Files:**
- Create: `legacy/README.md`
- Move: `main.py` to `legacy/v0.1.0/main.py`
- Move: `README.md`, `README.zh-CN.md` to `legacy/v0.1.0/`
- Move: `src/modelscope_image_gen/` to `legacy/v0.1.0/src/modelscope_image_gen/`
- Move: `.github/workflows/ci.yml` to `legacy/v0.1.0/.github/workflows/ci.yml`
- Move: the seven selected behavior tests plus `service_test_helpers.py` to `legacy/v0.1.0/tests/`
- Remove from the rebuild branch: old project metadata, unselected tests, and tracked `.DS_Store` files.

**Interfaces:**
- Consumes: exact archive manifest in 08 and tag `legacy/v0.1.0` for full history.
- Produces: a read-only evidence directory with no root-project participation.

- [ ] **Step 1: Verify all move sources resolve inside the workspace**

Run a PowerShell check using `Resolve-Path` for every selected source and assert every resolved path starts with `D:\Code\modelscope-image-gen\`. Do not start recursive moves if any source is missing or outside that root.

- [ ] **Step 2: Move the approved files with Git-aware operations**

Run:

```powershell
New-Item -ItemType Directory -Force legacy/v0.1.0/src,legacy/v0.1.0/.github/workflows,legacy/v0.1.0/tests | Out-Null
git mv main.py legacy/v0.1.0/main.py
git mv README.md legacy/v0.1.0/README.md
git mv README.zh-CN.md legacy/v0.1.0/README.zh-CN.md
git mv src/modelscope_image_gen legacy/v0.1.0/src/modelscope_image_gen
git mv .github/workflows/ci.yml legacy/v0.1.0/.github/workflows/ci.yml
git mv tests/service_test_helpers.py legacy/v0.1.0/tests/service_test_helpers.py
git mv tests/test_client.py legacy/v0.1.0/tests/test_client.py
git mv tests/test_server_errors.py legacy/v0.1.0/tests/test_server_errors.py
git mv tests/test_service_async_flow.py legacy/v0.1.0/tests/test_service_async_flow.py
git mv tests/test_service_generate_errors.py legacy/v0.1.0/tests/test_service_generate_errors.py
git mv tests/test_service_generate_outputs.py legacy/v0.1.0/tests/test_service_generate_outputs.py
git mv tests/test_service_generate_polling.py legacy/v0.1.0/tests/test_service_generate_polling.py
```

Expected: only the approved semantic assets appear under `legacy/v0.1.0`.

- [ ] **Step 3: Remove obsolete tracked root files without touching ignored user data**

Run:

```powershell
git rm .DS_Store src/.DS_Store .gitignore .python-version pyproject.toml uv.lock tests/conftest.py tests/test_config.py tests/test_task_store.py
```

Expected: `.venv`, `.ruff_cache`, `outputs`, and all ignored runtime data remain untouched.

- [ ] **Step 4: Create the legacy index**

Create `legacy/README.md` with this content:

```markdown
# Legacy implementation archive

`legacy/v0.1.0/` preserves the minimum semantic evidence from the former 0.1.0 implementation.

- Source commit: `42c0709`
- Annotated tag: `legacy/v0.1.0`
- Baseline verified on 2026-07-10: 28 tests passed; Ruff passed.
- Preserved here: core Python source, the old entry point, bilingual README files, the old CI workflow, and selected behavior tests.
- Full historical project metadata, lock file, unselected tests, and exact dependency environment remain available from the Git tag.

Inherit behavior and lessons, not structure. New code must not import this directory, and root build, test, lint, type-check, and package commands must exclude it.
```

- [ ] **Step 5: Verify the archive manifest and commit**

Run:

```powershell
$expected = @(
    'legacy/v0.1.0/.github/workflows/ci.yml'
    'legacy/v0.1.0/README.md'
    'legacy/v0.1.0/README.zh-CN.md'
    'legacy/v0.1.0/main.py'
    'legacy/v0.1.0/tests/service_test_helpers.py'
    'legacy/v0.1.0/tests/test_client.py'
    'legacy/v0.1.0/tests/test_server_errors.py'
    'legacy/v0.1.0/tests/test_service_async_flow.py'
    'legacy/v0.1.0/tests/test_service_generate_errors.py'
    'legacy/v0.1.0/tests/test_service_generate_outputs.py'
    'legacy/v0.1.0/tests/test_service_generate_polling.py'
)
$expected += git ls-files 'legacy/v0.1.0/src/modelscope_image_gen/**'
$actual = git ls-files 'legacy/v0.1.0/**'
$difference = Compare-Object ($expected | Sort-Object -Unique) ($actual | Sort-Object -Unique)
if ($difference) { $difference | Format-Table; throw 'Legacy manifest mismatch' }
```

Then run:

```powershell
git add legacy
git diff --cached --check
git commit -m "chore: archive v0.1.0 implementation"
```

Expected: the commit contains only legacy moves, legacy documentation, and removal of obsolete tracked old-project files.

### Task 3: Establish the Python 3.14 uv project metadata

**Files:**
- Create: `.python-version`
- Create: `.gitignore`
- Create: `pyproject.toml`
- Create: `README.md`
- Create: `README.zh-CN.md`
- Create: `LICENSE`
- Create: `SECURITY.md`
- Create: `CHANGELOG.md`
- Generate: `uv.lock`

**Interfaces:**
- Consumes: dependency decisions from 02 and data exclusions from 04.
- Produces: the single dependency/build truth used by every later task.

- [ ] **Step 1: Create the runtime and ignore files**

`.python-version`:

```text
3.14
```

`.gitignore`:

```gitignore
__pycache__/
*.py[cod]
*.egg-info/
.pytest_cache/
.ruff_cache/
.coverage
htmlcov/
build/
dist/
.venv/
.env
.env.*
!.env.example
outputs/
.modelscope-image-gen/
*.sqlite3
*.sqlite3-wal
*.sqlite3-shm
*.tmp
.DS_Store
```

- [ ] **Step 2: Create `pyproject.toml` with the locked toolchain**

```toml
[project]
name = "modelscope-image-gen-mcp"
version = "0.2.0"
description = "Local-first MCP server for reliable ModelScope image generation"
readme = "README.md"
requires-python = ">=3.14,<3.15"
license = "MIT"
dependencies = [
    "mcp==2.0.0b1",
    "anyio>=4.14,<5",
    "httpx>=0.28.1,<1",
    "pydantic>=2.13.4,<2.14",
    "pydantic-settings>=2.14,<3",
    "aiosqlite>=0.22,<1",
    "platformdirs>=4,<5",
    "Pillow>=12.3,<13",
]

[project.scripts]
modelscope-image-gen-mcp = "modelscope_image_gen.cli:main"

[dependency-groups]
dev = [
    "mcp[cli]==2.0.0b1",
    "pytest>=9,<10",
    "pytest-cov",
    "ruff>=0.14,<0.15",
    "ty==0.0.58",
]

[build-system]
requires = ["uv_build>=0.11.28,<0.12"]
build-backend = "uv_build"

[tool.uv]
required-version = ">=0.11.28,<0.12"
prerelease = "allow"

[tool.ruff]
target-version = "py314"
line-length = 120
extend-exclude = ["legacy"]

[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP", "N", "ASYNC", "RUF"]

[tool.pytest.ini_options]
minversion = "9.0"
addopts = "-ra --strict-config --strict-markers"
testpaths = ["tests"]
markers = [
    "live: requires explicit ModelScope credentials and network access",
]

[tool.coverage.run]
branch = true
source = ["modelscope_image_gen"]
```

- [ ] **Step 3: Create honest root documentation and license files**

`README.md`:

```markdown
# ModelScope Image Gen MCP

Local-first MCP v2 server for reliable ModelScope text-to-image generation.

The 0.2.0 rebuild targets Python 3.14 and uses uv. Its default Agent workflow is `submit_image_generation` → `check_image_generation` → `fetch_image_generation_result`; no generation tool is implemented during Phase 0.

See `docs/rebuild/08-implementation-brief.md` for the approved contract.
```

`README.zh-CN.md`:

```markdown
# ModelScope Image Gen MCP

一个本地优先、面向可靠 ModelScope 文生图任务的 MCP v2 Server。

0.2.0 重构目标为 Python 3.14，并统一使用 uv。Agent 默认工作流是 `submit_image_generation` → `check_image_generation` → `fetch_image_generation_result`；Phase 0 尚不实现生图工具。

完整契约见 `docs/rebuild/08-implementation-brief.md`。
```

`SECURITY.md`:

```markdown
# Security

ModelScope tokens, prompts, SQLite state, WAL/SHM files, provider locators, and generated artifacts are sensitive. Never include them in public issues. Report vulnerabilities privately to the repository owner and rotate any token that may have been exposed.
```

`CHANGELOG.md`:

```markdown
# Changelog

## [Unreleased]

### Changed

- Began the clean 0.2.0 rebuild on Python 3.14, uv, and MCP v2.
```

`LICENSE` is the standard MIT license text with:

```text
Copyright (c) 2026 ModelScope Image Gen MCP contributors
```

- [ ] **Step 4: Upgrade the local uv executable if needed and resolve the lock**

Run:

```powershell
uv --version
uv self update
uv --version
uv lock
uv sync --locked --all-groups
```

Expected: uv is within `>=0.11.28,<0.12`; Python 3.14 is selected; `mcp==2.0.0b1` and `mcp-types==2.0.0b1` resolve because prereleases are explicitly allowed; Pydantic remains `<2.14`.

- [ ] **Step 5: Verify metadata and commit**

Run:

```powershell
uv lock --check
uv tree --depth 1
git add .python-version .gitignore pyproject.toml uv.lock README.md README.zh-CN.md LICENSE SECURITY.md CHANGELOG.md
git diff --cached --check
git commit -m "build: establish Python 3.14 project foundation"
```

### Task 4: Add the lightweight CLI and empty tools-only MCP server

**Files:**
- Create: `src/modelscope_image_gen/__init__.py`
- Create: `src/modelscope_image_gen/__main__.py`
- Create: `src/modelscope_image_gen/cli.py`
- Create: `src/modelscope_image_gen/bootstrap.py`
- Create: `src/modelscope_image_gen/mcp_adapter/__init__.py`
- Create: `src/modelscope_image_gen/mcp_adapter/server.py`
- Test: `tests/e2e/test_cli.py`
- Test: `tests/contract/mcp/test_server_foundation.py`

**Interfaces:**
- Produces: `package_version() -> str`, `create_server() -> Server[None]`, `run_stdio_server() -> None`, and `main(argv: Sequence[str] | None = None) -> int`.

- [ ] **Step 1: Write failing CLI and capability tests**

```python
# tests/e2e/test_cli.py
from importlib.metadata import version
from pathlib import Path
import subprocess
import sys


def test_module_version_matches_distribution() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "modelscope_image_gen", "--version"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert result.stdout.strip() == version("modelscope-image-gen-mcp")
    assert result.stderr == ""


def test_import_does_not_create_files(tmp_path: Path) -> None:
    result = subprocess.run(
        [sys.executable, "-c", "import modelscope_image_gen"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    )
    assert list(tmp_path.iterdir()) == []
    assert result.stdout == ""
    assert result.stderr == ""
```

```python
# tests/contract/mcp/test_server_foundation.py
from modelscope_image_gen.mcp_adapter.server import create_server


def test_server_declares_only_tools_capability() -> None:
    options = create_server().create_initialization_options()
    assert options.server_name == "modelscope-image-gen-mcp"
    assert options.title == "ModelScope Image Generation"
    assert options.capabilities.tools is not None
    assert options.capabilities.tools.list_changed is False
    assert options.capabilities.prompts is None
    assert options.capabilities.resources is None
    assert options.capabilities.completions is None
```

- [ ] **Step 2: Run the focused tests and verify they fail**

Run:

```powershell
uv run pytest tests/e2e/test_cli.py tests/contract/mcp/test_server_foundation.py -v
```

Expected: collection fails because the new package modules do not exist.

- [ ] **Step 3: Implement the minimal package, server, bootstrap, and CLI**

```python
# src/modelscope_image_gen/__init__.py
from importlib.metadata import version


def package_version() -> str:
    return version("modelscope-image-gen-mcp")
```

```python
# src/modelscope_image_gen/mcp_adapter/server.py
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from mcp import types
from mcp.server import Server
from mcp.server.lowlevel.server import ServerRequestContext

from modelscope_image_gen import package_version


@asynccontextmanager
async def _lifespan(_: Server[None]) -> AsyncIterator[None]:
    yield None


async def _list_tools(
    _context: ServerRequestContext[None],
    _params: types.PaginatedRequestParams | None,
) -> types.ListToolsResult:
    return types.ListToolsResult(tools=[])


def create_server() -> Server[None]:
    return Server(
        "modelscope-image-gen-mcp",
        version=package_version(),
        title="ModelScope Image Generation",
        instructions=(
            "Prefer submit_image_generation, then check_image_generation, then "
            "fetch_image_generation_result for long-running image generation. "
            "Use list_image_generations to recover previously created jobs. "
            "Use generate_image only when the caller can wait synchronously."
        ),
        lifespan=_lifespan,
        on_list_tools=_list_tools,
    )
```

```python
# src/modelscope_image_gen/bootstrap.py
from mcp.server.stdio import stdio_server

from modelscope_image_gen.mcp_adapter.server import create_server


async def run_stdio_server() -> None:
    server = create_server()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )
```

```python
# src/modelscope_image_gen/cli.py
import argparse
from collections.abc import Sequence

import anyio

from modelscope_image_gen import package_version
from modelscope_image_gen.bootstrap import run_stdio_server


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="modelscope-image-gen-mcp")
    parser.add_argument("--version", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.version:
        print(package_version())
        return 0
    anyio.run(run_stdio_server)
    return 0
```

```python
# src/modelscope_image_gen/__main__.py
from modelscope_image_gen.cli import main

raise SystemExit(main())
```

Keep both new `__init__.py` files otherwise empty except for the shown version helper in the package root.

- [ ] **Step 4: Run focused and quality checks**

Run:

```powershell
uv run pytest tests/e2e/test_cli.py tests/contract/mcp/test_server_foundation.py -v
uv run ruff check src tests
uv run ty check
```

Expected: all commands pass.

- [ ] **Step 5: Commit**

```powershell
git add src tests/e2e tests/contract
git commit -m "feat: add MCP v2 server foundation"
```

### Task 5: Add side-effect-free settings, path resolution, and stderr logging

**Files:**
- Create: `src/modelscope_image_gen/infrastructure/__init__.py`
- Create: `src/modelscope_image_gen/infrastructure/config/__init__.py`
- Create: `src/modelscope_image_gen/infrastructure/config/settings.py`
- Create: `src/modelscope_image_gen/infrastructure/config/paths.py`
- Create: `src/modelscope_image_gen/infrastructure/config/logging.py`
- Modify: `src/modelscope_image_gen/cli.py`
- Test: `tests/unit/infrastructure/test_settings.py`
- Test: `tests/unit/infrastructure/test_paths.py`
- Test: `tests/unit/infrastructure/test_logging.py`

**Interfaces:**
- Produces: `Settings`, `ResolvedPaths`, `resolve_paths(settings)`, and `configure_logging(level)`.

- [ ] **Step 1: Write failing tests for missing token, stable paths, and stderr logging**

```python
# tests/unit/infrastructure/test_settings.py
from pydantic import SecretStr

from modelscope_image_gen.infrastructure.config.settings import Settings


def test_missing_token_is_allowed() -> None:
    settings = Settings(_env_file=None)
    assert settings.modelscope_sdk_token is None


def test_token_is_redacted() -> None:
    settings = Settings(_env_file=None, modelscope_sdk_token=SecretStr("SENTINEL_TOKEN"))
    assert "SENTINEL_TOKEN" not in repr(settings)


def test_api_base_is_normalized() -> None:
    settings = Settings(_env_file=None, api_base="https://example.com/api")
    assert settings.api_base == "https://example.com/api/"
```

```python
# tests/unit/infrastructure/test_paths.py
from pathlib import Path

from modelscope_image_gen.infrastructure.config.paths import resolve_paths
from modelscope_image_gen.infrastructure.config.settings import Settings


def test_default_paths_do_not_depend_on_cwd(monkeypatch, tmp_path: Path) -> None:
    settings = Settings(_env_file=None)
    before = resolve_paths(settings)
    monkeypatch.chdir(tmp_path)
    after = resolve_paths(settings)
    assert before == after
    assert before.data_dir.is_absolute()


def test_explicit_paths_override_data_dir(tmp_path: Path) -> None:
    settings = Settings(
        _env_file=None,
        data_dir=tmp_path / "data",
        database_path=tmp_path / "custom.sqlite3",
        artifact_root=tmp_path / "images",
    )
    paths = resolve_paths(settings)
    assert paths.database_path == (tmp_path / "custom.sqlite3").resolve()
    assert paths.artifact_root == (tmp_path / "images").resolve()
```

```python
# tests/unit/infrastructure/test_logging.py
import logging

from modelscope_image_gen.infrastructure.config.logging import configure_logging


def test_logging_uses_stderr_only(capsys) -> None:
    configure_logging("INFO")
    logging.getLogger("modelscope_image_gen").info("server.ready")
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "level=INFO event=server.ready" in captured.err
```

- [ ] **Step 2: Run focused tests and verify import failures**

```powershell
uv run pytest tests/unit/infrastructure -v
```

Expected: collection fails because the infrastructure config modules do not exist.

- [ ] **Step 3: Implement the approved Settings model, paths, and logging**

```python
# src/modelscope_image_gen/infrastructure/config/settings.py
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

LogLevel = Literal["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="MODELSCOPE_IMAGE_GEN_",
        extra="ignore",
        populate_by_name=True,
    )

    modelscope_sdk_token: SecretStr | None = Field(
        default=None,
        validation_alias="MODELSCOPE_SDK_TOKEN",
    )
    api_base: str = "https://api-inference.modelscope.cn/"
    default_model: str = "Qwen/Qwen-Image"
    data_dir: Path | None = None
    database_path: Path | None = None
    artifact_root: Path | None = None
    submit_timeout_seconds: float = Field(default=30, gt=0)
    status_timeout_seconds: float = Field(default=30, gt=0)
    download_timeout_seconds: float = Field(default=60, gt=0)
    blocking_poll_interval_seconds: float = Field(default=5, gt=0)
    default_max_wait_seconds: float = Field(default=600, gt=0)
    max_concurrent_downloads: int = Field(default=4, ge=1)
    max_download_bytes: int = Field(default=52_428_800, gt=0)
    max_image_pixels: int = Field(default=40_000_000, gt=0)
    log_level: LogLevel = "INFO"
    terminal_job_retention_days: int = Field(default=0, ge=0)
    temp_file_retention_hours: int = Field(default=24, ge=0)

    @field_validator("api_base")
    @classmethod
    def validate_api_base(cls, value: str) -> str:
        normalized = value.strip().rstrip("/") + "/"
        parsed = urlsplit(normalized)
        if parsed.scheme != "https" or not parsed.netloc:
            raise ValueError("api_base must be an HTTPS URL")
        return normalized

    @field_validator("default_model")
    @classmethod
    def validate_default_model(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("default_model must not be empty")
        return normalized
```

```python
# src/modelscope_image_gen/infrastructure/config/paths.py
from dataclasses import dataclass
from pathlib import Path

from platformdirs import user_data_path

from modelscope_image_gen.infrastructure.config.settings import Settings


@dataclass(frozen=True, slots=True)
class ResolvedPaths:
    data_dir: Path
    database_path: Path
    artifact_root: Path


def _absolute(path: Path) -> Path:
    return path.expanduser().resolve()


def resolve_paths(settings: Settings) -> ResolvedPaths:
    default_data = user_data_path("modelscope-image-gen-mcp", appauthor=False)
    data_dir = _absolute(settings.data_dir or default_data)
    database_path = _absolute(settings.database_path or data_dir / "state.sqlite3")
    artifact_root = _absolute(settings.artifact_root or data_dir / "artifacts")
    return ResolvedPaths(data_dir, database_path, artifact_root)
```

```python
# src/modelscope_image_gen/infrastructure/config/logging.py
import logging
import sys
from datetime import UTC, datetime


class KeyValueFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        timestamp = datetime.fromtimestamp(record.created, UTC).isoformat().replace("+00:00", "Z")
        return f"timestamp={timestamp} level={record.levelname} event={record.getMessage()}"


def configure_logging(level: str) -> None:
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(KeyValueFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)
```

- [ ] **Step 4: Wire logging into CLI without parsing Token eagerly elsewhere**

Replace the final part of `main` with:

```python
    settings = Settings(_env_file=None)
    configure_logging(settings.log_level)
    anyio.run(run_stdio_server)
    return 0
```

and add imports for `Settings` and `configure_logging`. Do not resolve paths or create directories in Phase 0 startup.

- [ ] **Step 5: Run focused and global checks**

```powershell
uv run pytest tests/unit/infrastructure tests/e2e/test_cli.py -v
uv run ruff check src tests
uv run ty check
```

- [ ] **Step 6: Commit**

```powershell
git add src/modelscope_image_gen/infrastructure src/modelscope_image_gen/cli.py tests/unit
git commit -m "feat: add side-effect-free runtime configuration"
```

### Task 6: Add architecture, stdio, wheel, and cross-platform CI gates

**Files:**
- Create: `tests/architecture/test_import_boundaries.py`
- Create: `tests/conftest.py`
- Create: `tests/e2e/stdio/test_stdio_foundation.py`
- Create: `scripts/verify_wheel.py`
- Create: `.github/workflows/ci.yml`

**Interfaces:**
- Consumes: CLI, empty tools server, project metadata, and archive layout.
- Produces: executable Phase 0 completion gates for local and CI use.

- [ ] **Step 1: Write the architecture test**

```python
# tests/architecture/test_import_boundaries.py
import ast
from pathlib import Path

ROOT = Path(__file__).parents[2]
SRC = ROOT / "src"


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_new_source_never_imports_legacy() -> None:
    for path in SRC.rglob("*.py"):
        assert not any(name == "legacy" or name.startswith("legacy.") for name in _imports(path))


def test_root_has_no_legacy_entrypoint() -> None:
    assert not (ROOT / "main.py").exists()
    assert not (SRC / "legacy").exists()
```

- [ ] **Step 2: Write the real stdio test**

```python
# tests/conftest.py
import pytest


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"
```

```python
# tests/e2e/stdio/test_stdio_foundation.py
from io import StringIO
import sys

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


@pytest.mark.anyio
async def test_stdio_server_initializes_with_empty_tools() -> None:
    params = StdioServerParameters(command=sys.executable, args=["-m", "modelscope_image_gen"])
    errlog = StringIO()
    async with stdio_client(params, errlog=errlog) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            initialized = await session.initialize()
            tools = await session.list_tools()
    assert initialized.server_info.name == "modelscope-image-gen-mcp"
    assert initialized.capabilities.tools is not None
    assert initialized.capabilities.prompts is None
    assert initialized.capabilities.resources is None
    assert tools.tools == []
```

- [ ] **Step 3: Write `scripts/verify_wheel.py`**

```python
from pathlib import Path
import subprocess
import zipfile


def main() -> None:
    wheels = list(Path("dist").glob("*.whl"))
    if len(wheels) != 1:
        raise SystemExit(f"expected one wheel, found {len(wheels)}")
    wheel = wheels[0]
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
    if not any(name.endswith("modelscope_image_gen/cli.py") for name in names):
        raise SystemExit("wheel is missing the package CLI")
    forbidden = ("legacy/", ".env", ".sqlite3", ".png", ".jpg", "docs/rebuild/")
    leaked = [name for name in names if any(value in name.lower() for value in forbidden)]
    if leaked:
        raise SystemExit(f"forbidden wheel content: {leaked}")
    result = subprocess.run(
        ["uvx", "--from", str(wheel), "modelscope-image-gen-mcp", "--version"],
        check=True,
        capture_output=True,
        text=True,
    )
    if result.stdout.strip() != "0.2.0":
        raise SystemExit(f"unexpected installed version: {result.stdout!r}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Create Windows and Ubuntu CI**

```yaml
name: CI

on:
  push:
  pull_request:

jobs:
  verify:
    strategy:
      fail-fast: false
      matrix:
        os: [ubuntu-latest, windows-latest]
    runs-on: ${{ matrix.os }}
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v6
        with:
          version: "0.11.28"
          enable-cache: true
      - run: uv python install 3.14
      - run: uv lock --check
      - run: uv sync --locked --all-groups
      - run: uv run ruff format --check
      - run: uv run ruff check
      - run: uv run ty check
      - run: uv run pytest
      - run: uv build --no-sources
      - run: uv run python scripts/verify_wheel.py
```

- [ ] **Step 5: Run the complete Phase 0 gate**

```powershell
uv lock --check
uv sync --locked --all-groups
uv run ruff format --check
uv run ruff check
uv run ty check
uv run pytest
uv build --no-sources
uv run python scripts/verify_wheel.py
```

Expected: every command exits zero; stdio test reports zero tools and Tools-only capabilities; wheel version output is `0.2.0`; no legacy path is packaged.

- [ ] **Step 6: Commit**

```powershell
git add .github scripts tests/architecture tests/e2e/stdio
git diff --cached --check
git commit -m "ci: verify the rebuild foundation"
```

### Task 7: Record Phase 0 completion without overstating later phases

**Files:**
- Modify: `CHANGELOG.md`
- Modify: this plan by checking completed boxes during execution.

**Interfaces:**
- Produces: a verified Phase 0 handoff into the submit vertical-slice plan.

- [ ] **Step 1: Re-run all evidence commands from a clean worktree**

Run `git status --short`, all Phase 0 gate commands, and `git log --oneline --decorate -8`. Expected: no unexplained files, tag and branch are correct, and all gates pass.

- [ ] **Step 2: Update completion language**

Record only these claims in CHANGELOG/report: clean Python 3.14 foundation, tools-only empty MCP v2 server, settings/path/logging foundation, cross-platform CI definition, and verified wheel. Explicitly state that no image-generation tool is implemented until Phase 1.

- [ ] **Step 3: Commit the Phase 0 record**

```powershell
git add CHANGELOG.md docs/superpowers/plans/2026-07-10-rebuild-phase-0-foundation.md
git commit -m "docs: record rebuild foundation completion"
```

After this commit, create the separate Phase 1 submit vertical-slice plan before implementing domain or Provider behavior.
