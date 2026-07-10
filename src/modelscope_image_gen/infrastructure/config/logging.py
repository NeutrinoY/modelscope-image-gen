from __future__ import annotations

import logging
import sys
from datetime import UTC, datetime


class _UtcFormatter(logging.Formatter):
    converter = lambda *args: datetime.now(UTC).timetuple()  # noqa: E731


def configure_logging(level: str) -> None:
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(_UtcFormatter("timestamp=%(asctime)sZ level=%(levelname)s event=%(message)s"))
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    # HTTPX logs complete request URLs at INFO, including provider task paths and image locators.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
