# Changelog

This file records user-visible behavior, compatibility boundaries, and release-relevant fixes. It does not mirror individual commits or replace the project history in the README.

## [Unreleased]

The current source tree targets `0.2.1`. Until a `v0.2.1` tag is created, these changes describe the next repository release rather than a published release.

### Fixed

- Reject malformed successful ModelScope responses instead of treating a single image URL as a sequence of characters.
- Apply the `generate_image` local wait budget across status checks and artifact fetching.
- Persist each fetched image in its own short, cancellation-shielded transaction so completed artifacts survive sibling cancellation.
- Preserve stable `PERSISTENCE_ERROR` and `CONCURRENT_MODIFICATION` codes at the MCP boundary.
- Isolate `.env.local` tests from externally configured live-test tokens.

### Changed

- Moved image HTTP-response lifecycles into the ModelScope Provider while keeping the Artifact Store provider-neutral.
- Replaced persisted absolute artifact paths with controlled relative paths and application-level resolved views.
- Reduced `list_image_generations` to a privacy-minimized SQLite summary projection.
- Centralized application next-step policy while keeping MCP tool-name mapping inside the adapter.
- Made GitHub source installation through `uvx --from git+https://...` the documented user path; local source checkout remains the development path.
- Deferred PyPI, TestPyPI, MCP Registry, and GitHub Release work until an independent distribution channel is justified.
- Removed the unpublished `server.json` manifest because it referenced a PyPI distribution owned by another project.
- Updated CI to `actions/checkout@v7` and the current resolvable `astral-sh/setup-uv@v8.3.2` release, with read-only checkout, duplicate-run cancellation, and job time limits.

### Security

- Added canonical UUID, relative-path, SHA-256, symlink, and Windows junction/reparse-point validation.
- Hardened atomic replacement, bounded inspection of existing files, corrupted-artifact recovery, and startup cleanup.
- Kept prompts, provider image locators, raw upstream bodies, and absolute artifact paths out of list results and default logs.

### Verified

- Exercised all five tools through real ModelScope workflows and multiple real stdio MCP hosts.
- Verified 1024×1024 and 768×768 PNG generation, SHA-256 consistency, idempotent fetches, and installed-wheel stdio startup.
- Verified remote Git installation from the pushed rebuild branch with `uvx --prerelease=allow --from ...`, returning version `0.2.1`.
- Expanded the default automated suite to 39 tests plus one opt-in live test.

## [0.2.0] - 2026-07-11

`0.2.0` is a complete rebuild. It turns the first working ModelScope wrapper into a persistent, recoverable local task system for MCP agents and long-running image generation.

### Added

- Established the fixed five-tool workflow: `submit_image_generation`, `check_image_generation`, `fetch_image_generation_result`, `list_image_generations`, and `generate_image`.
- Added local Job discovery, multi-image Jobs, partial artifact success, and independent retries for unfinished images.
- Added concrete Pydantic input and output contracts, structured `ok/data/error` envelopes, concise text summaries, and explicit next actions.
- Added a controlled Artifact Store with streaming byte limits, image and pixel validation, SHA-256 metadata, and atomic file commits.

### Changed

- Replaced per-Job JSON files with a versioned SQLite store that reconstructs complete Job and image state.
- Made submit → check → fetch the recommended workflow while retaining `generate_image` as a blocking convenience tool.
- Persisted submission intent before the external request and added explicit recovery for uncertain outcomes.
- Separated upstream Job success from per-image artifact delivery.
- Changed the default model to `krea/Krea-2-Turbo`.
- Moved to MCP Python SDK v2 and a tools-only low-level server.

### Security and privacy

- Removed agent-controlled output directories and filenames.
- Excluded tokens and Authorization headers from persistence and tool output.
- Excluded prompts, provider image locators, raw upstream bodies, tracebacks, and artifact absolute paths from default logs.
- Kept artifacts under paths derived from controlled identifiers inside the configured Artifact Root.

### Compatibility

`0.2.0` intentionally does not provide a compatibility layer for `0.1.0`:

- `get_image_generation_status` became `check_image_generation`.
- `get_image_generation_result` became `fetch_image_generation_result`.
- `list_image_generations` was added for local recovery.
- Image size changed from a `WIDTHxHEIGHT` string to a `{width, height}` object.
- Output paths, filenames, polling intervals, backoff, and maximum poll attempts were removed from tool inputs.
- `timeout` was removed as a persisted Job state; a local wait limit now hands the active Job back to the caller.
- Legacy JSON Job files are not migrated into the SQLite store.

### Verified

- Passed formatting, lint, type checking, automated tests, package builds, package-content audits, and isolated-wheel startup.
- Passed the official in-memory MCP client contract path and a real submit → check → fetch workflow with the default model.

The repository tag records the `0.2.0` source milestone; no PyPI or MCP Registry publication was part of that release.

## [0.1.0] - 2026-03-10

`0.1.0` established the project's first complete working direction in a single development session.

### Added

- Connected ModelScope text-to-image generation to MCP.
- Added blocking generation and asynchronous submit, status, and result tools.
- Stored local Job state so later MCP calls could continue earlier work.
- Added structured errors with stage, retryability, retry timing, and request diagnostics.
- Added separate submit, status, and download timeouts.
- Validated downloaded image bytes, including images returned as `application/octet-stream`.

### Historical limitations

- Stored each Job in a separate JSON file using mutable dictionary state.
- Coupled workflow code to MCP protocol types through a Mixin-based service.
- Represented a local timeout as a terminal Job state.
- Preserved only the first returned image.
- Allowed agents to choose output directories and filenames.
- Duplicated submission, polling, download, and error handling across blocking and asynchronous paths.

These limitations became design input for the `0.2.0` rebuild rather than compatibility requirements. The final prototype baseline is preserved read-only under [`legacy/v0.1.0/`](legacy/v0.1.0/).
