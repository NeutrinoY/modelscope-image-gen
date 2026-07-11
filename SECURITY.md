# Security Policy

## Supported versions

Security fixes are developed for the current `0.2.x` source line on this repository. The archived prototype is retained for historical reference only.

| Version | Security support |
|---|---|
| Current `main` / `0.2.x` source line | Supported |
| `legacy/v0.1.0` | Not supported |

Only code distributed from this repository is covered by this policy. The project currently published on PyPI under the name `modelscope-image-gen-mcp` is maintained separately and is **not** a release of this repository.

## Git source identity

The documented installation path executes source obtained from `github.com/NeutrinoY/modelscope-image-gen`. Verify the repository owner and URL before placing them in an MCP host configuration; do not substitute an unreviewed fork.

The default `@main` reference is intentionally movable and follows the latest accepted source. Operators that require an immutable or auditable installation should replace `main` with a trusted tag or commit. uv caches Git and tool data, so use cache refresh options deliberately rather than forcing a network refresh on every host start.

## Reporting a vulnerability

Use GitHub's private vulnerability reporting when **Security → Report a vulnerability** is available for this repository. If that option is unavailable, open a minimal public issue asking the maintainer to establish a private reporting channel. Do not include vulnerability details or sensitive data in that issue.

Please include, when safe:

- the affected version, tag, or commit;
- the operating system and MCP host;
- reproduction steps using placeholders instead of live secrets or private data;
- the expected and observed behavior;
- the likely impact and any known mitigation.

Do not disclose a live ModelScope token, Authorization header, signed image URL, private prompt, generated private image, SQLite database, WAL/SHM file, or exploitable filesystem path in a public issue.

## Sensitive local data

The server intentionally persists enough information to recover Jobs across MCP calls and process restarts. Treat the following as sensitive:

- `state.sqlite3`, its WAL/SHM files, and backups;
- prompts and negative prompts stored in SQLite;
- ModelScope Task references and signed provider image locators stored in SQLite;
- generated images and temporary artifact files;
- MCP host configuration containing `MODELSCOPE_SDK_TOKEN`.

The token and Authorization header must never be stored in SQLite or returned by tools. `stdout` is reserved for MCP protocol traffic; runtime logs are written to `stderr` and should still be handled as operational data.

## Token exposure response

If a token may have been exposed:

1. Revoke or rotate it immediately in ModelScope.
2. Stop MCP host and server processes that inherited the old environment.
3. Remove the token from host configuration, shell history, logs, screenshots, and CI secrets.
4. Inspect repository history, MCP host configuration, uv caches, and build artifacts before publishing or sharing them.
5. Restart the server only after installing the replacement token.

## Filesystem and resource boundary

Artifact files must remain under the configured Artifact Root. Reports involving path traversal, symlink or Windows reparse-point escape, unsafe cleanup, unintended overwrite, unbounded downloads, decompression bombs, or bypasses of byte and pixel limits are security-sensitive.
