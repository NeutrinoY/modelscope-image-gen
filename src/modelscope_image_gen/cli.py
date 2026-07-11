from __future__ import annotations

import argparse

import anyio

from modelscope_image_gen import __version__
from modelscope_image_gen.bootstrap import serve_stdio


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="modelscope-image-gen-mcp")
    parser.add_argument("--version", action="version", version=__version__)
    return parser


def main() -> None:
    _parser().parse_args()
    anyio.run(serve_stdio, backend="asyncio")
