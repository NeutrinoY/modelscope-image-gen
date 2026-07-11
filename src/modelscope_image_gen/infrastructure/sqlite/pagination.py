from __future__ import annotations

import base64
import hashlib
import json
from datetime import datetime

from modelscope_image_gen.domain import JobId


def filter_fingerprint(statuses: tuple[str, ...]) -> str:
    return hashlib.sha256(",".join(statuses).encode()).hexdigest()[:16]


def encode_cursor(updated_at: str, job_id: str, fingerprint: str) -> str:
    payload = json.dumps({"v": 1, "u": updated_at, "j": job_id, "f": fingerprint}, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(payload).decode().rstrip("=")


def decode_cursor(value: str, fingerprint: str) -> tuple[str, str]:
    try:
        padded = value + "=" * (-len(value) % 4)
        decoded = base64.b64decode(padded, altchars=b"-_", validate=True)
        payload = json.loads(decoded.decode())
        if not isinstance(payload, dict) or payload.get("v") != 1 or payload.get("f") != fingerprint:
            raise ValueError
        updated_at = payload.get("u")
        job_id = payload.get("j")
        if not isinstance(updated_at, str) or not isinstance(job_id, str):
            raise ValueError
        datetime.fromisoformat(updated_at)
        JobId(job_id)
        return updated_at, job_id
    except Exception as exc:
        raise ValueError("INVALID_CURSOR") from exc
