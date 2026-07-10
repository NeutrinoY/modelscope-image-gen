# Security Policy

## Supported versions

Security fixes are developed for the current `0.2.x` line. The archived `0.1.0` implementation under `legacy/` is not supported and must not be deployed as the current server.

## Reporting a vulnerability

Please use GitHub's private security advisory reporting for this repository. Do not open a public issue containing a live ModelScope token, Authorization header, signed image URL, private prompt, generated private image, database, WAL/SHM file, or exploitable filesystem path.

Include, when safe:

- affected version or commit;
- operating system and MCP Host;
- reproduction steps using placeholders rather than live secrets;
- expected and observed behavior;
- impact and suggested mitigation.

## Sensitive local data

The server intentionally persists enough information to recover jobs. Treat the following as sensitive:

- `state.sqlite3`, its WAL/SHM files, and backups;
- prompts and negative prompts stored in SQLite;
- ModelScope task references and signed provider image locators stored in SQLite;
- generated images and temporary artifact files;
- MCP Host configuration containing `MODELSCOPE_SDK_TOKEN`.

The token and Authorization header must never be stored in SQLite or returned by tools. stdout is reserved for MCP protocol traffic; logs are written to stderr.

## Token exposure response

If a token is exposed:

1. revoke or rotate it immediately in ModelScope;
2. stop MCP Host processes that inherited the old environment;
3. remove the token from Host configuration, shell history, logs, screenshots, and CI secrets;
4. inspect repository history and build artifacts before publishing anything;
5. restart the server only after installing the replacement token.

## Filesystem boundary

Artifact files must remain under the configured artifact root. Reports involving path traversal, symlink/reparse-point escape, unsafe cleanup, unbounded downloads, decompression bombs, or unintended file overwrite are considered security-sensitive.
