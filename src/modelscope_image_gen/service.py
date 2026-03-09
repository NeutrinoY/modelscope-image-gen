from __future__ import annotations

# pyright: reportMissingImports=false
import asyncio
import logging
import os
from io import BytesIO

import httpx
from mcp import types
from PIL import Image

from .client import ModelScopeClient
from .config import Settings

logger = logging.getLogger("modelscope-image-gen")


class ImageGenerationService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = ModelScopeClient(
            api_base=settings.modelscope_api_base,
            api_key=settings.modelscope_sdk_token,
        )

    async def generate_image(
        self,
        *,
        prompt: str,
        model: str,
        size: str,
        output_filename: str,
        output_dir: str,
        poll_interval_seconds: float | None,
        max_poll_attempts: int | None,
        poll_backoff: bool | None,
        max_poll_interval_seconds: float | None,
        negative_prompt: str | None,
        seed: int | None,
    ) -> list[types.TextContent]:
        try:
            os.makedirs(output_dir, exist_ok=True)
            output_path = os.path.join(output_dir, output_filename)

            cfg = self.settings.polling_defaults()
            base_interval = (
                poll_interval_seconds
                if poll_interval_seconds is not None
                else float(cfg["base_interval"])
            )
            max_attempts = (
                max_poll_attempts if max_poll_attempts is not None else int(cfg["max_attempts"])
            )
            use_backoff = poll_backoff if poll_backoff is not None else bool(cfg["backoff"])
            max_interval = (
                max_poll_interval_seconds
                if max_poll_interval_seconds is not None
                else float(cfg["max_interval"])
            )

            logger.info("正在使用模型 %s 生成图片，提示词: %s", model, prompt)

            async with httpx.AsyncClient(timeout=60.0) as client:
                submit_response = await self.client.submit_generation(
                    client,
                    model=model,
                    prompt=prompt,
                    size=size,
                    negative_prompt=negative_prompt,
                    seed=seed,
                )
                submit_data = submit_response.json()
                task_id = submit_data.get("task_id")
                submit_request_id = submit_response.headers.get("X-Request-Id")
                if not task_id:
                    return [
                        types.TextContent(
                            type="text",
                            text=(
                                "任务提交失败\n"
                                f"status_code: {submit_response.status_code}\n"
                                f"request_id: {submit_request_id}\n"
                                f"body: {submit_data}"
                            ),
                        )
                    ]

                attempt = 0
                while attempt < max_attempts:
                    wait_time = (
                        base_interval
                        if not use_backoff
                        else min(base_interval * (2**attempt), max_interval)
                    )
                    await asyncio.sleep(wait_time)
                    attempt += 1

                    poll_response = await self.client.poll_task(client, task_id=task_id)
                    poll_data = poll_response.json()
                    task_status = poll_data.get("task_status")
                    poll_request_id = poll_response.headers.get("X-Request-Id")
                    logger.info(
                        "任务状态: %s (尝试 %s/%s, wait=%.2fs)",
                        task_status,
                        attempt,
                        max_attempts,
                        wait_time,
                    )

                    if task_status == "SUCCEED":
                        output_images = poll_data.get("output_images", [])
                        if not output_images:
                            return [types.TextContent(type="text", text="任务成功但没有输出图片")]

                        image_url = output_images[0]
                        image_response = await self.client.download_image(
                            client, image_url=image_url
                        )
                        image_request_id = image_response.headers.get("X-Request-Id")
                        content_type = image_response.headers.get("Content-Type", "")
                        if not content_type.startswith("image/"):
                            return [
                                types.TextContent(
                                    type="text",
                                    text=(
                                        "图片下载失败：返回的内容不是图片\n"
                                        f"status_code: {image_response.status_code}\n"
                                        f"request_id: {image_request_id}\n"
                                        f"content_type: {content_type}"
                                    ),
                                )
                            ]

                        image = Image.open(BytesIO(image_response.content))
                        try:
                            if output_path.lower().endswith((".jpg", ".jpeg")) and image.mode in (
                                "RGBA",
                                "P",
                            ):
                                image = image.convert("RGB")
                            image.save(output_path)
                        except Exception as save_err:  # noqa: BLE001
                            return [
                                types.TextContent(type="text", text=f"图片保存失败: {save_err}")
                            ]

                        return [
                            types.TextContent(
                                type="text",
                                text=(
                                    "图片生成成功！\n"
                                    f"提示词: {prompt}\n"
                                    f"模型: {model}\n"
                                    f"分辨率: {size}\n"
                                    f"保存路径: {os.path.abspath(output_path)}\n"
                                    f"输出目录: {os.path.abspath(output_dir)}\n"
                                    f"文件名: {output_filename}\n"
                                    f"图片URL: {image_url}\n"
                                    f"request_id: {poll_request_id or submit_request_id}"
                                ),
                            )
                        ]

                    if task_status == "FAILED":
                        error_msg = poll_data.get("message", "任务失败")
                        status_code = (
                            poll_data.get("status_code")
                            or poll_data.get("code")
                            or poll_response.status_code
                        )
                        return [
                            types.TextContent(
                                type="text",
                                text=(
                                    f"图片生成失败: {error_msg}\n"
                                    f"status_code: {status_code}\n"
                                    f"request_id: {poll_request_id}\n"
                                    f"body: {poll_data}"
                                ),
                            )
                        ]

                return [
                    types.TextContent(
                        type="text",
                        text=(
                            "图片生成超时，任务可能仍在处理中\n"
                            f"max_attempts: {max_attempts}\n"
                            f"base_interval: {base_interval}\n"
                            f"backoff: {use_backoff}\n"
                            f"max_interval: {max_interval}"
                        ),
                    )
                ]
        except httpx.HTTPStatusError as http_err:
            resp = http_err.response
            status_code = getattr(resp, "status_code", None)
            request_id = resp.headers.get("X-Request-Id") if resp else None
            body = resp.text if resp else None
            return [
                types.TextContent(
                    type="text",
                    text=(
                        "请求失败\n"
                        f"status_code: {status_code}\n"
                        f"request_id: {request_id}\n"
                        f"body: {body}"
                    ),
                )
            ]
        except Exception as err:  # noqa: BLE001
            return [types.TextContent(type="text", text=f"生成图片时发生错误: {err}")]
