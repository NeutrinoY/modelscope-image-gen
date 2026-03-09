from __future__ import annotations

# pyright: reportMissingImports=false, reportAttributeAccessIssue=false
from mcp import types

SUPPORTED_TOOL_NAMES = {
    "generate_image",
    "submit_image_generation",
    "get_image_generation_status",
    "get_image_generation_result",
}


def build_tool_list(default_model: str) -> list[types.Tool]:
    return [
        types.Tool(
            name="submit_image_generation",
            description="Start a non-blocking image generation job and return a job_id for later status/result calls",
            inputSchema={
                "type": "object",
                "properties": {
                    "prompt": {"type": "string", "description": "Required. Main generation prompt"},
                    "model": {
                        "type": "string",
                        "description": f"Optional. Model name (default: {default_model})",
                        "default": default_model,
                    },
                    "size": {
                        "type": "string",
                        "description": "Optional. Output resolution in WIDTHxHEIGHT format (for example: 1024x1024)",
                        "default": "1024x1024",
                    },
                    "output_filename": {"type": "string", "description": "Optional. Local output filename", "default": "result_image.jpg"},
                    "output_dir": {"type": "string", "description": "Optional. Local output directory path", "default": "./outputs"},
                    "poll_interval_seconds": {
                        "type": "number",
                        "description": "Optional. Base polling interval in seconds for subsequent status checks",
                    },
                    "max_poll_attempts": {
                        "type": "integer",
                        "description": "Optional. Max polling attempts used by status/result follow-up tools",
                    },
                    "poll_backoff": {"type": "boolean", "description": "Optional. Enable exponential polling backoff"},
                    "max_poll_interval_seconds": {
                        "type": "number",
                        "description": "Optional. Max polling interval in seconds when backoff is enabled",
                    },
                    "negative_prompt": {"type": "string", "description": "Optional. Negative prompt to suppress unwanted styles/artifacts"},
                    "seed": {"type": "integer", "description": "Optional. Random seed for reproducibility"},
                },
                "required": ["prompt"],
            },
        ),
        types.Tool(
            name="get_image_generation_status",
            description="Check job progress by job_id. Use this after submit_image_generation until state is terminal",
            inputSchema={
                "type": "object",
                "properties": {"job_id": {"type": "string", "description": "Required. job_id returned by submit_image_generation"}},
                "required": ["job_id"],
            },
        ),
        types.Tool(
            name="get_image_generation_result",
            description="Fetch and save the final image by job_id. Call when status indicates the job is ready",
            inputSchema={
                "type": "object",
                "properties": {"job_id": {"type": "string", "description": "Required. job_id returned by submit_image_generation"}},
                "required": ["job_id"],
            },
        ),
        types.Tool(
            name="generate_image",
            description="Blocking convenience API: submit, poll, download, and save in one call",
            inputSchema={
                "type": "object",
                "properties": {
                    "prompt": {"type": "string", "description": "Required. Main generation prompt"},
                    "model": {
                        "type": "string",
                        "description": f"Optional. Model name (default: {default_model})",
                        "default": default_model,
                    },
                    "size": {
                        "type": "string",
                        "description": "Optional. Output resolution in WIDTHxHEIGHT format. Qwen-Image supports 64x64 to 1664x1664. Default: 1024x1024",
                        "default": "1024x1024",
                    },
                    "output_filename": {
                        "type": "string",
                        "description": "Optional. Local output filename (default: result_image.jpg)",
                        "default": "result_image.jpg",
                    },
                    "output_dir": {
                        "type": "string",
                        "description": "Optional. Local output directory path (default: ./outputs)",
                        "default": "./outputs",
                    },
                    "poll_interval_seconds": {"type": "number", "description": "Optional. Base polling interval in seconds (default: env or 5)"},
                    "max_poll_attempts": {
                        "type": "integer",
                        "description": "Optional. Max poll attempts (default: env or 120, about 10 minutes)",
                    },
                    "poll_backoff": {
                        "type": "boolean",
                        "description": "Optional. Enable exponential polling backoff (default: env or false)",
                    },
                    "max_poll_interval_seconds": {
                        "type": "number",
                        "description": "Optional. Max polling interval in seconds when backoff is enabled (default: env or 30)",
                    },
                    "negative_prompt": {"type": "string", "description": "Optional. Negative prompt to suppress unwanted styles/artifacts"},
                    "seed": {"type": "integer", "description": "Optional. Random seed for reproducibility"},
                },
                "required": ["prompt"],
            },
        ),
    ]
