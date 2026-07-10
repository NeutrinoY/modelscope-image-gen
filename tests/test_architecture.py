from __future__ import annotations

import ast
from pathlib import Path

SRC = Path("src/modelscope_image_gen")


def project_imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names if alias.name.startswith("modelscope_image_gen"))
        elif isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("modelscope_image_gen"):
            imports.add(node.module)
    return imports


def test_layer_dependencies_and_legacy_boundary() -> None:
    for path in SRC.rglob("*.py"):
        imports = project_imports(path)
        assert all("legacy" not in name for name in imports)
        relative = path.relative_to(SRC).as_posix()
        if relative.startswith("domain/"):
            assert all(name.startswith("modelscope_image_gen.domain") for name in imports)
        elif relative.startswith("application/"):
            assert not any(
                name.startswith(("modelscope_image_gen.infrastructure", "modelscope_image_gen.mcp_adapter"))
                for name in imports
            )
        elif relative.startswith("mcp_adapter/"):
            assert not any(name.startswith("modelscope_image_gen.infrastructure") for name in imports)
        elif relative == "cli.py":
            assert imports <= {"modelscope_image_gen", "modelscope_image_gen.bootstrap"}
