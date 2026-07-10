from __future__ import annotations

# pyright: reportMissingImports=false, reportAttributeAccessIssue=false
import json
from typing import Any

import httpx
from mcp import types

RETRYABLE_HTTP_STATUS = {408, 409, 425, 429, 500, 502, 503, 504}
_SENSITIVE_KEYS = {
    "authorization",
    "api_key",
    "apikey",
    "token",
    "access_token",
    "refresh_token",
    "password",
    "secret",
    "cookie",
    "set-cookie",
    "modelscope_sdk_token",
}


def _redact_text(value: str) -> str:
    lower = value.lower()
    markers = ["token=", "api_key=", "apikey=", "password="]
    for marker in markers:
        idx = lower.find(marker)
        if idx == -1:
            continue
        start = idx + len(marker)
        end = value.find("&", start)
        if end == -1:
            end = len(value)
        value = value[:start] + "[REDACTED]" + value[end:]
        lower = value.lower()

    if "bearer " in lower:
        parts = value.split("Bearer ")
        if len(parts) >= 2:
            first = parts[0]
            tail = []
            for part in parts[1:]:
                token_end = part.find(" ")
                if token_end == -1:
                    tail.append("[REDACTED]")
                else:
                    tail.append("[REDACTED]" + part[token_end:])
            value = first + "Bearer ".join(tail)

    return value


def _redact_data(value: Any) -> Any:
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, val in value.items():
            if str(key).lower() in _SENSITIVE_KEYS:
                out[str(key)] = "[REDACTED]"
            else:
                out[str(key)] = _redact_data(val)
        return out
    if isinstance(value, list):
        return [_redact_data(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_redact_data(item) for item in value)
    if isinstance(value, str):
        return _redact_text(value)
    return value


def parse_retry_after_seconds(value: str | None) -> int | None:
    if not value:
        return None
    try:
        seconds = int(value.strip())
        return seconds if seconds >= 0 else None
    except ValueError:
        return None


def stringify_body(response: httpx.Response | None) -> str | None:
    if response is None:
        return None
    try:
        return str(_redact_data(response.text))
    except Exception:  # noqa: BLE001
        return None


def build_error_payload(
    *,
    stage: str,
    reason_code: str,
    category: str,
    retryable: bool,
    retry_after_seconds: int | None = None,
    status_code: int | None = None,
    request_id: str | None = None,
    detail: str | None = None,
    suggestion: str | None = None,
    body: Any | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "stage": stage,
        "reason_code": reason_code,
        "category": category,
        "retryable": retryable,
        "retry_after_seconds": retry_after_seconds,
    }
    if status_code is not None:
        payload["status_code"] = status_code
    if request_id:
        payload["request_id"] = request_id
    if detail:
        payload["detail"] = str(_redact_data(detail))
    if suggestion:
        payload["suggestion"] = suggestion
    if body is not None:
        payload["body"] = _redact_data(body)
    return payload


def _build_error_text(title: str, payload: dict[str, Any]) -> str:
    mirrored = {"ok": False, "error": payload}
    return f"{title}\n\nJSON:\n{json.dumps(mirrored, ensure_ascii=False)}"


def _build_success_text(message: str, data: dict[str, Any]) -> str:
    mirrored = {"ok": True, "data": data}
    return f"{message}\n\nJSON:\n{json.dumps(mirrored, ensure_ascii=False)}"


def build_tool_error_result(title: str, **kwargs: Any) -> types.CallToolResult:
    payload = build_error_payload(**kwargs)
    return types.CallToolResult(
        isError=True,
        content=[types.TextContent(type="text", text=_build_error_text(title, payload))],
        structuredContent={"ok": False, "error": payload},
    )


def build_tool_error_result_from_payload(title: str, payload: dict[str, Any]) -> types.CallToolResult:
    return types.CallToolResult(
        isError=True,
        content=[types.TextContent(type="text", text=_build_error_text(title, payload))],
        structuredContent={"ok": False, "error": payload},
    )


def build_tool_success_result(message: str, data: dict[str, Any]) -> types.CallToolResult:
    return types.CallToolResult(
        isError=False,
        content=[types.TextContent(type="text", text=_build_success_text(message, data))],
        structuredContent={"ok": True, "data": data},
    )
