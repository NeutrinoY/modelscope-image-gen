from __future__ import annotations

from pathlib import Path

from platformdirs import user_data_path

APP_NAME = "modelscope-image-gen-mcp"


def default_data_dir() -> Path:
    return Path(user_data_path(APP_NAME, appauthor=False, ensure_exists=False))


def resolve_data_paths(
    *, data_dir: Path | None, database_path: Path | None, artifact_root: Path | None
) -> tuple[Path, Path, Path]:
    root = (data_dir or default_data_dir()).expanduser().resolve()
    database = (database_path or root / "state.sqlite3").expanduser().resolve()
    artifacts = (artifact_root or root / "artifacts").expanduser().resolve()
    return root, database, artifacts
