# ModelScope Image Gen MCP

Local-first MCP v2 server for reliable ModelScope text-to-image generation.

The 0.2.0 rebuild targets Python 3.14 and uses uv. Its default Agent workflow is `submit_image_generation` → `check_image_generation` → `fetch_image_generation_result`; no generation tool is implemented during Phase 0.

See `docs/rebuild/08-implementation-brief.md` for the approved contract.
