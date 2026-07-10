from __future__ import annotations

import json
from typing import Any

import httpx


class ModelScopeClient:
    def __init__(
        self,
        *,
        api_base: str,
        api_key: str,
        submit_timeout_seconds: float = 30.0,
        poll_timeout_seconds: float = 30.0,
        download_timeout_seconds: float = 60.0,
    ) -> None:
        self.api_base = api_base.rstrip("/") + "/"
        self.api_key = api_key
        self.submit_timeout_seconds = submit_timeout_seconds
        self.poll_timeout_seconds = poll_timeout_seconds
        self.download_timeout_seconds = download_timeout_seconds

    def _submit_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "X-ModelScope-Async-Mode": "true",
        }

    def _poll_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "X-ModelScope-Task-Type": "image_generation",
        }

    async def submit_generation(
        self,
        client: httpx.AsyncClient,
        *,
        model: str,
        prompt: str,
        size: str,
        negative_prompt: str | None,
        seed: int | None,
    ) -> httpx.Response:
        payload: dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "size": size,
        }
        if negative_prompt is not None:
            payload["negative_prompt"] = negative_prompt
        if seed is not None:
            payload["seed"] = seed

        response = await client.post(
            f"{self.api_base}v1/images/generations",
            headers=self._submit_headers(),
            content=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            timeout=self.submit_timeout_seconds,
        )
        response.raise_for_status()
        return response

    async def poll_task(self, client: httpx.AsyncClient, *, task_id: str) -> httpx.Response:
        response = await client.get(
            f"{self.api_base}v1/tasks/{task_id}",
            headers=self._poll_headers(),
            timeout=self.poll_timeout_seconds,
        )
        response.raise_for_status()
        return response

    async def download_image(self, client: httpx.AsyncClient, *, image_url: str) -> httpx.Response:
        response = await client.get(image_url, timeout=self.download_timeout_seconds)
        response.raise_for_status()
        return response
