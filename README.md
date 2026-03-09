# modelscope-image-gen-mcp

Modern Python MCP server for ModelScope async image generation.

## Usage

Set token:

```bash
export MODELSCOPE_SDK_TOKEN="your_token"
```

Install and run from project entrypoint:

```bash
uv sync --dev
uv run python main.py
```

Tool name: `generate_image`

Core arguments (compatible with legacy behavior):
- `prompt` (required)
- `model` (default: `Qwen/Qwen-Image`)
- `size` (default: `1024x1024`)
- `output_filename` (default: `result_image.jpg`)
- `output_dir` (default: `./outputs`)
- `poll_interval_seconds` / `max_poll_attempts` / `poll_backoff` / `max_poll_interval_seconds`

New optional arguments:
- `negative_prompt` (string)
- `seed` (integer)
