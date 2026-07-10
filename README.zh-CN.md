# ModelScope Image Gen MCP

一个本地优先、面向可靠 ModelScope 文生图任务的 MCP v2 Server。

0.2.0 重构目标为 Python 3.14，并统一使用 uv。Agent 默认工作流是 `submit_image_generation` → `check_image_generation` → `fetch_image_generation_result`；Phase 0 尚不实现生图工具。

完整契约见 `docs/rebuild/08-implementation-brief.md`。
