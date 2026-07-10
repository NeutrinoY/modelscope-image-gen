# Changelog

This file records user-visible changes, compatibility boundaries, and release verification for ModelScope Image Gen MCP. It summarizes releases rather than mirroring individual commits.

## [0.2.0] - 2026-07-11

0.2.0 is a complete rebuild of the project. It turns the first working ModelScope wrapper into a persistent, recoverable local task system designed for MCP Agents and long-running image generation.

The release focuses on preserving clear local truth: what was submitted, what ModelScope has confirmed, what remains uncertain, which artifacts are available, and what an Agent should do next.

### Highlights

- Established the fixed five-tool workflow: `submit_image_generation`, `check_image_generation`, `fetch_image_generation_result`, `list_image_generations`, and `generate_image`.
- Made submit → check → fetch the recommended default for schedulable Agents while retaining a blocking convenience tool.
- Added local task discovery so a lost Job ID no longer means a lost workflow.
- Added multi-image Jobs, partial artifact success, and independent retries for unfinished images.
- Changed the default model to `krea/Krea-2-Turbo`.

### Persistence and recovery

- Replaced isolated per-Job JSON files with a versioned SQLite store that reconstructs complete Job and image state.
- Persisted submission intent before contacting ModelScope so process interruption does not silently erase the local record.
- Added explicit recovery for uncertain submissions and prohibited automatic resubmission when the first request may already have reached ModelScope.
- Preserved active Job state across temporary network failures, local wait limits, and unknown Provider status values.

### Artifact delivery

- Replaced Agent-controlled output directories and filenames with a Server-controlled local Artifact Store.
- Added streaming download limits, image validation, pixel limits, SHA-256 metadata, atomic file commits, and safe path derivation.
- Made available artifacts idempotent: repeated fetch calls return existing files instead of downloading or overwriting them again.
- Kept formal Job data and generated images outside package and `uvx` environments so upgrades do not remove user artifacts.

### MCP and Agent experience

- Moved to MCP Python SDK v2 and a Tools-only low-level Server.
- Added concrete Pydantic input and output contracts for every tool.
- Standardized structured `ok/data/error` envelopes and concise TextContent summaries.
- Added strong next actions for check and fetch handoff, retry timing, and uncertain-submission warnings.
- Kept Provider image locators, prompts, raw upstream bodies, and internal exceptions out of normal MCP text responses.

### Compatibility changes

0.2.0 intentionally does not provide a compatibility layer for the 0.1.0 interface.

- `get_image_generation_status` was replaced by `check_image_generation`.
- `get_image_generation_result` was replaced by `fetch_image_generation_result`.
- `list_image_generations` was added for local discovery and recovery.
- Image size changed from a `WIDTHxHEIGHT` string to a `{width, height}` object.
- Agent-supplied output directories, output filenames, polling intervals, backoff, and maximum poll attempts were removed from tool inputs.
- `timeout` was removed as a persisted Job state; a local wait limit now hands the active Job back to the caller.
- Legacy JSON Job files are not migrated into the new SQLite store.

### Security and privacy

- Tokens and Authorization headers are excluded from persistence and tool output.
- Default logs suppress HTTP request URLs so Provider task paths and image locators are not written to stderr.
- Prompts, Provider image locators, raw upstream bodies, tracebacks, and artifact absolute paths are excluded from default logs.
- Artifact paths are derived from controlled identifiers and remain inside the configured Artifact Root.

### Verification

- Passed Ruff formatting and lint checks, ty type checking, automated tests, package builds, and package-content audits.
- Passed the official in-memory MCP Client contract path.
- Passed isolated wheel installation and real stdio subprocess smoke testing.
- Completed a real ModelScope submit → check → fetch run with the default `krea/Krea-2-Turbo` model and saved a validated 1024×1024 PNG.
- External MCP Host verification, Ubuntu CI execution, and actual PyPI/MCP Registry publication remain separate release operations.

## [0.1.0] - 2026-03-10

0.1.0 established the first complete working direction for the project. The main implementation was created between the evening of March 9 and the early morning of March 10, moving from a new uv scaffold to an asynchronous ModelScope image-generation MCP service in a single development session.

### Highlights

- Connected ModelScope text-to-image generation to MCP.
- Added a blocking `generate_image` tool for one-call generation.
- Added asynchronous submission, status, and result tools for long-running work.
- Stored Job state locally so later MCP calls could continue an earlier request.
- Added structured success and error results with stage, retryability, retry timing, and request diagnostics.
- Added separate submit, status, and download timeouts.
- Validated downloaded image bytes, including valid images returned as `application/octet-stream`.
- Added automated tests for request construction, polling, errors, image decoding, and local saving.

### Historical limitations

0.1.0 was a successful prototype, but its internal model still reflected the speed at which it was created:

- Job state was stored in one JSON file per task and represented by mutable dictionaries.
- Workflow code was assembled through a Mixin-based service and returned MCP protocol types directly.
- Timeout was represented as a terminal Job state.
- Only the first returned image was preserved.
- Agents could choose output directories and filenames.
- Blocking and asynchronous paths duplicated parts of submission, polling, download, and error handling.

These limitations became the design input for the 0.2.0 rebuild rather than compatibility requirements.

### Archive

On July 10, 2026, the 0.1.0 documentation and structured payload presentation were polished before the implementation was archived as `legacy/v0.1.0`. The annotated archive tag points to the final 0.1.0 baseline, while the release date remains March 10, when the working version was originally completed.
