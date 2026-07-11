from __future__ import annotations

RETRYABLE_STATUS_CODES = frozenset({408, 409, 425, 429, 500, 502, 503, 504})


def retry_after_seconds(value: str | None) -> int | None:
    try:
        parsed = int(value) if value is not None else None
        return parsed if parsed is not None and parsed >= 0 else None
    except ValueError:
        return None
