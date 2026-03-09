from __future__ import annotations

# pyright: reportAttributeAccessIssue=false
import logging
import os

import httpx
from mcp import types

from ..payloads import RETRYABLE_HTTP_STATUS, build_tool_error_result, build_tool_success_result, parse_retry_after_seconds, stringify_body

logger = logging.getLogger("modelscope-image-gen")


class ServiceGenerateWorkflow:
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
    ) -> types.CallToolResult:
        try:
            self.settings.require_api_key()
            os.makedirs(output_dir, exist_ok=True)
            output_path = os.path.join(output_dir, output_filename)
            base_interval, max_attempts, use_backoff, max_interval = self._resolve_polling_config(
                poll_interval_seconds=poll_interval_seconds,
                max_poll_attempts=max_poll_attempts,
                poll_backoff=poll_backoff,
                max_poll_interval_seconds=max_poll_interval_seconds,
            )
            logger.info("正在使用模型 %s 生成图片，提示词: %s", model, prompt)

            async with httpx.AsyncClient(timeout=60.0) as client:
                submit_phase = await self._submit_generation_phase(
                    client,
                    model=model,
                    prompt=prompt,
                    size=size,
                    negative_prompt=negative_prompt,
                    seed=seed,
                )
                if isinstance(submit_phase, types.CallToolResult):
                    return submit_phase
                task_id, submit_request_id = submit_phase

                poll_phase = await self._poll_generation_phase(
                    client,
                    task_id=task_id,
                    submit_request_id=submit_request_id,
                    base_interval=base_interval,
                    max_attempts=max_attempts,
                    use_backoff=use_backoff,
                    max_interval=max_interval,
                )
                if isinstance(poll_phase, types.CallToolResult):
                    return poll_phase
                image_url, poll_request_id = poll_phase

                decode_phase = await self._download_decode_phase(client, image_url=image_url)
                if isinstance(decode_phase, types.CallToolResult):
                    return decode_phase
                image, _ = decode_phase

                save_error = self._save_image_phase(image=image, output_path=output_path)
                if save_error is not None:
                    return save_error

                message = (
                    "图片生成成功！\n"
                    f"提示词: {prompt}\n"
                    f"模型: {model}\n"
                    f"分辨率: {size}\n"
                    f"保存路径: {os.path.abspath(output_path)}\n"
                    f"输出目录: {os.path.abspath(output_dir)}\n"
                    f"文件名: {output_filename}\n"
                    f"图片URL: {image_url}\n"
                    f"request_id: {poll_request_id or submit_request_id}"
                )
                return build_tool_success_result(
                    message,
                    data={
                        "prompt": prompt,
                        "model": model,
                        "size": size,
                        "output_path": os.path.abspath(output_path),
                        "output_dir": os.path.abspath(output_dir),
                        "output_filename": output_filename,
                        "image_url": image_url,
                        "request_id": poll_request_id or submit_request_id,
                    },
                )
        except ValueError as err:
            return build_tool_error_result(
                "配置错误",
                stage="validation",
                reason_code="MISSING_API_KEY",
                category="validation",
                retryable=False,
                detail=str(err),
                suggestion="设置环境变量 MODELSCOPE_SDK_TOKEN 后重试",
            )
        except httpx.HTTPStatusError as http_err:
            resp = http_err.response
            status_code = getattr(resp, "status_code", None)
            request_id = resp.headers.get("X-Request-Id") if resp else None
            body = stringify_body(resp)
            retry_after_seconds = parse_retry_after_seconds(resp.headers.get("Retry-After") if resp else None)

            stage = "request"
            reason_code = "HTTP_STATUS_ERROR"
            if resp is not None and resp.request is not None:
                path = resp.request.url.path
                if path.endswith("/v1/images/generations"):
                    stage = "submit"
                    reason_code = "SUBMIT_HTTP_ERROR"
                elif "/v1/tasks/" in path:
                    stage = "poll"
                    reason_code = "POLL_HTTP_ERROR"
                else:
                    stage = "download"
                    reason_code = "DOWNLOAD_HTTP_ERROR"

            retryable = isinstance(status_code, int) and status_code in RETRYABLE_HTTP_STATUS
            return build_tool_error_result(
                "请求失败",
                stage=stage,
                reason_code=reason_code,
                category="upstream_http",
                retryable=retryable,
                retry_after_seconds=retry_after_seconds,
                status_code=status_code,
                request_id=request_id,
                detail="上游接口返回非 2xx 状态码",
                suggestion="检查请求参数、鉴权令牌、服务可用性，并结合 body 与 request_id 排查",
                body=body,
            )
        except httpx.RequestError as req_err:
            request_url = str(req_err.request.url) if req_err.request else None
            return build_tool_error_result(
                "网络请求异常",
                stage="request",
                reason_code="NETWORK_ERROR",
                category="network",
                retryable=True,
                retry_after_seconds=1,
                detail=str(req_err),
                suggestion="检查网络连通性、DNS、代理与 TLS 配置",
                body=request_url,
            )
        except Exception as err:  # noqa: BLE001
            return build_tool_error_result(
                "生成图片时发生错误",
                stage="unexpected",
                reason_code="UNEXPECTED_ERROR",
                category="internal",
                retryable=False,
                detail=str(err),
                suggestion="查看服务端日志并携带请求参数进行复现",
            )
