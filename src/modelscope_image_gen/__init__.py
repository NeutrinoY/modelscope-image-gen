"""ModelScope Image Gen MCP."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("modelscope-image-gen-mcp")
except PackageNotFoundError:
    __version__ = "0.2.1"

__all__ = ["__version__"]
