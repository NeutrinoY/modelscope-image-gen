from __future__ import annotations

import ast
from pathlib import Path

SRC = Path("src/modelscope_image_gen")


def module_imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.update(f"{node.module}.{alias.name}" for alias in node.names)
    return imports


def test_layer_dependencies_and_legacy_boundary() -> None:
    for path in SRC.rglob("*.py"):
        all_imports = module_imports(path)
        imports = {name for name in all_imports if name.startswith("modelscope_image_gen")}
        assert all("legacy" not in name for name in all_imports)
        relative = path.relative_to(SRC).as_posix()
        if relative.startswith("domain/"):
            assert all(name.startswith("modelscope_image_gen.domain") for name in imports)
        elif relative.startswith("application/"):
            assert "typing.Any" not in all_imports
            assert not any(
                name.startswith(("modelscope_image_gen.infrastructure", "modelscope_image_gen.mcp_adapter"))
                for name in imports
            )
        elif relative.startswith("mcp_adapter/"):
            assert not any(name.startswith("modelscope_image_gen.infrastructure") for name in imports)
        elif relative == "cli.py":
            assert all(
                name == "modelscope_image_gen"
                or name.startswith("modelscope_image_gen.__version__")
                or name.startswith("modelscope_image_gen.bootstrap")
                for name in imports
            )
        if relative.startswith("infrastructure/artifacts/"):
            assert not any(name == "httpx" or name.startswith("httpx.") for name in all_imports)
