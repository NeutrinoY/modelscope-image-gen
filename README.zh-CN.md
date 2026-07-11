<!-- mcp-name: io.github.neutrinoy/modelscope-image-gen -->

<div align="center">
  <h1>ModelScope Image Gen MCP</h1>
  <p><strong>可靠、可恢复、本地优先的 ModelScope 图像生成工作流</strong></p>
  <p>面向 MCP Agent、MCP Host 与本地自动化</p>
  <p><a href="README.md">English</a> · <strong>简体中文</strong></p>
</div>

---

图像生成并不总能在一次调用里结束。任务可能仍在排队，Agent 已经开始处理别的工作；MCP Host 也可能在图片完成前退出。真正棘手的不是发送请求，而是在等待、失败、恢复和结果落盘之间，持续保留可信的事实。

ModelScope Image Gen MCP 为这段不确定的过程提供一条明确路径：**提交任务、观察进度、找回上下文、获取产物**。每次生成都有持久化的本地 Job，Agent 不必维持一段漫长会话，也不需要解释 ModelScope 的原始响应。

- **可恢复**：Job 保存在 SQLite 中，可跨 MCP 调用和进程重启继续使用。
- **不伪造状态**：网络错误、本地等待到期和未知上游状态不会被写成任务失败。
- **面向多图片**：每张图片独立下载、验证、保存和重试。
- **产物受控**：服务端校验真实图片内容，并将文件原子保存到受控目录。
- **下一步明确**：结构化结果告诉 Agent 应继续 `check`、进入 `fetch`，还是停止自动重试。

## 🚀 快速开始

### 1. 准备源码环境

在源码目录中使用 Python 3.14 与 `uv >=0.11.28,<0.12`：

```bash
uv python install 3.14
uv sync --locked
uv run modelscope-image-gen-mcp --version
```

### 2. 配置 Token

从 ModelScope 获取 Token，并将它放入 MCP Host 的环境配置：

```text
MODELSCOPE_SDK_TOKEN=replace-with-your-modelscope-token
```

Token 不应作为工具参数交给 Agent，也不要提交到仓库。缺少 Token 不会阻止 Server 启动；本地列表、已经保存的终态 Job 和现有产物仍然可以读取。

### 3. 接入 MCP Host

将路径替换为当前源码工作区的绝对路径：

```json
{
  "mcpServers": {
    "modelscope-image-gen": {
      "command": "uv",
      "args": [
        "--directory",
        "D:/absolute/path/to/modelscope-image-gen",
        "run",
        "modelscope-image-gen-mcp"
      ],
      "env": {
        "MODELSCOPE_SDK_TOKEN": "replace-with-your-modelscope-token"
      }
    }
  }
}
```

`uv --directory` 负责切换源码目录，不依赖 Host 是否支持额外的 `cwd` 字段。保存配置并重启 Host 后，应能发现五个工具。

Windows 路径建议使用正斜杠；macOS 和 Linux 则替换为 `/absolute/path/to/modelscope-image-gen`。

也可以直接启动 stdio Server：

```bash
uv run modelscope-image-gen-mcp
```

`stdout` 只承载 MCP 协议；运行日志写入 `stderr`。

## 🔄 工作方式

推荐工作流将“创建外部任务”“观察任务状态”和“获取本地产物”分开：

```text
submit_image_generation
→ check_image_generation
→ 如果仍在运行，稍后再次 check_image_generation
→ fetch_image_generation_result
```

```mermaid
flowchart LR
    A[提交生成任务] --> B{本地 Job 状态}
    B -->|submitted / in_progress| C[检查一次上游状态]
    C --> B
    B -->|succeeded| D[下载并验证产物]
    B -->|failed| E[读取终态错误]
    D --> F[使用本地文件]
    G[从本地列表找回 Job] --> B
```

### 异步流程

异步流程适合 Agent 和能够安排后续调用的 MCP Host：

1. `submit_image_generation` 创建 ModelScope Task，并立即返回本地 Job ID；
2. `check_image_generation` 每次最多查询一次上游状态；
3. Job 进入 `succeeded` 后，`fetch_image_generation_result` 下载、验证并保存图片；
4. Job ID 丢失时，使用 `list_image_generations` 从本地 SQLite 找回任务。

一次调用不需要等待完整生图过程。Agent 可以在两次检查之间继续处理其他工作，甚至在新的会话中恢复同一个 Job。

### 阻塞式便利入口

`generate_image` 将 submit、check 和 fetch 组合为一次阻塞调用，适合简单脚本或短交互。它复用同一组应用用例，不维护第二套轮询和下载逻辑。

本地等待预算耗尽时，它会返回仍在运行的 Job 和下一步动作：

```text
completed=false
next_action.tool=check_image_generation
```

这不代表 ModelScope Task 已经超时或被取消。

## 🎯 适用场景

| 适合 | 不以此为目标 |
|---|---|
| 长耗时、需要稍后继续的文生图任务 | 一次请求即可返回的小型同步 API 包装 |
| 本机或可信工作站中的 MCP Agent | 公网多租户图像生成平台 |
| 需要跨调用、跨会话或重启恢复 Job | Web 或桌面图片管理界面 |
| 需要验证并持久化本地图片产物 | 图生图、参考图和图片编辑 |
| 希望获得稳定状态、错误和下一步动作 | 多 Provider 插件市场或队列集群 |
| stdio Host 与 Server 位于同一机器或共享文件目录 | 远程 HTTP 文件分发或 OAuth 控制面 |

项目专注于 **ModelScope 文本生成图片 + 本地 stdio MCP**，不提供上游取消、MCP Resources/Prompts、base64 图片传输或 Agent 控制删除。

## 🧰 工具速查

五个工具按固定顺序公开：

| 工具 | 用途 | 副作用 | 通常下一步 |
|---|---|---|---|
| `submit_image_generation` | 创建异步文生图任务 | 访问 ModelScope，可能消耗额度；非幂等 | `check_image_generation` |
| `check_image_generation` | 刷新一次活动 Job 状态 | 最多一次上游查询，并可能更新 SQLite | 继续 check 或进入 fetch |
| `fetch_image_generation_result` | 获取 succeeded Job 的图片 | 下载、验证并写入缺失产物 | partial 时再次 fetch |
| `list_image_generations` | 查询本地 Job 摘要 | 只读取 SQLite，不访问 ModelScope | 使用 Job ID 恢复流程 |
| `generate_image` | 阻塞编排 submit、check 和 fetch | 创建任务、等待、访问网络并写文件 | 完成，或转回异步流程 |

### 生成输入

最小输入只有 prompt：

```json
{
  "prompt": "云海之上的未来天文台"
}
```

完整输入：

```json
{
  "prompt": "云海之上的未来天文台，清晨，电影感建筑可视化",
  "model": "krea/Krea-2-Turbo",
  "size": {
    "width": 1024,
    "height": 1024
  },
  "negative_prompt": null,
  "seed": 42
}
```

| 字段 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `prompt` | string | 必填 | 去除首尾空白后必须非空 |
| `model` | string 或 null | `krea/Krea-2-Turbo` | 省略时使用服务端默认模型 |
| `size` | object | `1024 × 1024` | 使用 `{width, height}` 对象 |
| `negative_prompt` | string 或 null | null | 空字符串会规范化为 null |
| `seed` | integer 或 null | null | 提供时传给 ModelScope |
| `max_wait_seconds` | number 或 null | 服务端默认 | 仅用于 `generate_image`，范围 `1..3600` |

Agent 不能指定输出目录或最终文件名。下载字节、图片像素和并发安全上限也不能由工具参数覆盖。

### 本地任务查询

`list_image_generations` 支持：

| 字段 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `statuses` | JobStatus 数组或 null | null | 按 Job 状态过滤 |
| `limit` | integer | `20` | 范围 `1..100` |
| `cursor` | string 或 null | null | 不透明分页 cursor，只应原样复制 |

列表不会返回 prompt、Provider 图片地址或本地产物路径，也不会批量访问 ModelScope。

## 🧾 返回结果

每个已知工具都会同时返回：

- `structuredContent`：供 Agent 和自动化程序稳定解析的严格结果；
- `TextContent`：简洁说明本次操作、当前状态和下一步；
- `isError`：直接由结构化结果中的 `ok` 派生。

统一结构：

```json
{
  "ok": true,
  "data": {},
  "error": null
}
```

这里必须区分两层事实：

- `ok` 表示本次工具操作是否成功；
- `job.status` 表示生图任务本身处于什么状态。

因此，成功读取一个 `status=failed` 的终态 Job，仍然是一次成功的 check：`ok=true`。fetch 至少获得一张图片时，也会以 `ok=true`、`partial=true` 表达部分成功。

结构化结果还会在适当时返回：

```json
{
  "next_action": {
    "tool": "check_image_generation",
    "job_id": "019f...",
    "recommended_wait_seconds": 5
  }
}
```

Agent 不需要自行猜测下一步工具。

## 📦 本地产物

MCP 响应不会承载整张图片。服务先将图片保存为本机文件，再返回可定位、可验证的产物信息：

```text
ModelScope 任务成功
→ 下载图片字节
→ 验证格式、尺寸和像素
→ 原子保存到 Artifact Store
→ 写入 SQLite 元数据
→ 返回本地路径和 SHA-256
```

一张 available 图片通常包含：

```json
{
  "image_id": "019f...",
  "position": 0,
  "artifact_status": "available",
  "file_path": "C:/Users/.../artifacts/jobs/.../000-....png",
  "relative_path": "jobs/.../000-....png",
  "sha256": "...",
  "byte_size": 1034118,
  "media_type": "image/png",
  "format": "PNG",
  "width": 1024,
  "height": 1024
}
```

重复 fetch 时，已经 available 的图片直接返回，不会再次下载或覆盖。完整文件已原子保存但 SQLite 更新失败时，后续 fetch 可以重新检查文件并修复元数据。

**文件可见性：** `file_path` 是 Server 所在机器上的绝对路径。容器、沙箱、WSL、虚拟机或远程 Host 需要将 Artifact Root 挂载到双方都能访问的位置。本项目不通过 MCP Resources 或 base64 传输大文件。

## 🛡️ 可靠性语义

### Job 与产物是两层事实

Job 状态：

```text
submitting → submitted → in_progress → succeeded
          └──────────────────────────→ failed
```

单张产物状态：

```text
pending → available
       └→ failed
```

上游 Job 已经 `succeeded` 后，本地图片下载仍可能部分失败；这不会推翻 ModelScope 已经确认的成功事实。

### 不确定不等于失败

- 本地等待到期不是 Job 状态；
- check 网络失败不会把 Job 写成 `failed`；
- 未知 Provider 状态不会被猜测为 `in_progress` 或 `failed`；
- 调用取消不会被描述为上游 Task 已取消。

### 提交结果不确定

服务会在访问 ModelScope 之前先保存 `submitting` Job。如果请求可能已经到达 ModelScope，但本地没有获得可靠 Task ID，系统会记录：

```text
SUBMISSION_OUTCOME_UNKNOWN
possibly_submitted=true
```

> [!WARNING]
> 不要自动提交相同请求。第一次请求可能已经产生外部 Task 和额度消耗；自动重提可能创建重复任务。

### 多图片与部分成功

一个 succeeded Job 可以包含多张图片。每张图片独立保存错误和产物状态；再次 fetch 只处理未完成或失败的图片，不会丢弃已经可用的文件。

## 🔐 本地数据与隐私

正式 Job 和图片保存在当前用户的数据目录，而不是包安装目录、源码目录或 `uvx` 环境：

```text
<data_dir>/
├── state.sqlite3
└── artifacts/
    └── jobs/
        └── <job_id>/
            └── 000-<image_id>.<verified-extension>
```

典型默认位置：

```text
Windows: %LOCALAPPDATA%/modelscope-image-gen-mcp/
macOS:   ~/Library/Application Support/modelscope-image-gen-mcp/
Linux:   ~/.local/share/modelscope-image-gen-mcp/
```

SQLite 为了恢复 Job，会保存 prompt、negative prompt、ModelScope Task 引用、Provider 图片 locator、安全错误和产物元数据。因此以下内容都应被视为敏感本地数据：

- `state.sqlite3`、WAL/SHM 和备份；
- 生成图片与临时产物；
- 包含 Token 的 MCP Host 配置。

安全边界：

- Token 和 Authorization Header 不写入 SQLite；
- 工具返回不暴露 Provider 图片 locator；
- list 不返回 prompt 或产物路径；
- 默认日志不记录 prompt、locator、原始上游正文或产物绝对路径；
- stdout 只承载 MCP wire，日志写 stderr；
- 正式 Job 和图片默认不自动删除。

安全问题与 Token 泄漏处理见 [SECURITY.md](SECURITY.md)。

## ⚙️ 配置

常用配置：

| 环境变量 | 默认值 | 用途 |
|---|---:|---|
| `MODELSCOPE_SDK_TOKEN` | 空 | 访问 ModelScope 的秘密 Token |
| `MODELSCOPE_IMAGE_GEN_DEFAULT_MODEL` | `krea/Krea-2-Turbo` | 默认文生图模型 |
| `MODELSCOPE_IMAGE_GEN_DATA_DIR` | 平台用户数据目录 | 运行数据根目录 |
| `MODELSCOPE_IMAGE_GEN_ARTIFACT_ROOT` | `<data_dir>/artifacts` | 受控产物根目录 |
| `MODELSCOPE_IMAGE_GEN_DEFAULT_MAX_WAIT_SECONDS` | `600` | `generate_image` 的本地等待预算 |
| `MODELSCOPE_IMAGE_GEN_LOG_LEVEL` | `INFO` | `stderr` 日志等级 |

<details>
<summary>查看完整环境变量</summary>

| 环境变量 | 默认值 | 用途 |
|---|---:|---|
| `MODELSCOPE_IMAGE_GEN_API_BASE` | `https://api-inference.modelscope.cn/` | ModelScope HTTPS API 地址 |
| `MODELSCOPE_IMAGE_GEN_DATABASE_PATH` | `<data_dir>/state.sqlite3` | SQLite 数据库路径 |
| `MODELSCOPE_IMAGE_GEN_SUBMIT_TIMEOUT_SECONDS` | `30` | 提交 HTTP 超时 |
| `MODELSCOPE_IMAGE_GEN_STATUS_TIMEOUT_SECONDS` | `30` | 状态查询 HTTP 超时 |
| `MODELSCOPE_IMAGE_GEN_DOWNLOAD_TIMEOUT_SECONDS` | `60` | 图片下载 HTTP 超时 |
| `MODELSCOPE_IMAGE_GEN_BLOCKING_POLL_INTERVAL_SECONDS` | `5` | `generate_image` 的检查间隔 |
| `MODELSCOPE_IMAGE_GEN_MAX_CONCURRENT_DOWNLOADS` | `4` | 单次 fetch 的图片并发上限 |
| `MODELSCOPE_IMAGE_GEN_MAX_DOWNLOAD_BYTES` | `52428800` | 单张图片下载字节上限 |
| `MODELSCOPE_IMAGE_GEN_MAX_IMAGE_PIXELS` | `40000000` | 单张图片像素上限 |
| `MODELSCOPE_IMAGE_GEN_TERMINAL_JOB_RETENTION_DAYS` | `0` | `0` 表示不删除正式数据 |
| `MODELSCOPE_IMAGE_GEN_TEMP_FILE_RETENTION_HOURS` | `24` | `.part` 临时文件保留时间 |

</details>

完整可复制模板见 [.env.example](.env.example)。环境变量变化后需要重启 Server。

## 🩺 故障恢复

| 现象 | 处理方式 |
|---|---|
| `MODELSCOPE_TOKEN_MISSING` | 设置 Token 后重启 Server；本地 list 仍可使用 |
| `SUBMISSION_OUTCOME_UNKNOWN` | 不要自动重提；检查已有 Job 和诊断 request ID |
| check 返回 `NETWORK_ERROR` / `UPSTREAM_HTTP_ERROR` | Job 保持原状态；遵循 `retryable`、`retry_after_seconds` 和 `next_action` |
| `UPSTREAM_STATUS_UNKNOWN` | 稍后再次 check；不要猜测终态 |
| fetch 返回 partial | 再次调用 fetch；available 图片会被跳过 |
| Job ID 丢失 | 使用 list，可按 `statuses` 过滤并通过 cursor 翻页 |
| Host 找不到图片 | 检查 Host 是否能访问 Server 的 Artifact Root |
| 产物保存失败 | 检查目录权限、磁盘空间和安全软件；下次 fetch 可能修复已存在文件的元数据 |

## 🧱 架构

```text
mcp_adapter ───────┐
                   v
              application
                   v
                domain
                   ^
              application ports
                   ^
infrastructure ────┘

bootstrap → 唯一 composition root
cli       → bootstrap
```

- `domain/`：不可变业务事实、状态转换和不变量；
- `application/`：用例、端口、Provider outcome、结果与安全视图；
- `infrastructure/`：ModelScope HTTP、SQLite、Artifact Store、配置和锁；
- `mcp_adapter/`：Pydantic wire model、ToolContract、Handler、Presenter 和低层 MCP Server；
- `bootstrap.py`：资源构建、启动恢复和生命周期。

Provider 拥有 HTTP 请求和图片流生命周期；Artifact Store 只处理字节、验证和受控路径；MCP Adapter 不直接访问具体基础设施。

## 🕰️ 从原型到可靠工作流

这个项目并非一开始就拥有今天的形态。它经历的不是一条不断堆叠功能的版本线，而是一次次重新确认：面对长耗时、会中断、会失败的图像生成任务，系统究竟应该相信并保存哪些事实。

### `0.1.0` — 先证明方向成立

2026 年 3 月，项目最初在一个夜晚里完成了从空白骨架到可运行原型的跨越。它第一次证明：ModelScope 的异步生图任务可以通过 MCP 交给 Agent，长耗时过程也可以拆成提交、状态检查和结果获取。

那个版本已经拥有本地 Job、结构化错误和图片内容验证，但仍保留着原型的速度痕迹：逐任务 JSON、可变字典、单图片假设、重复工作流，以及由 Agent 决定输出路径。

它证明了“这件事可以做”，也留下了下一阶段更重要的问题：如果任务需要跨越会话和进程重启，系统怎样才能长期维护清楚、可信的状态？

最初版本现作为只读历史基线保存在 [`legacy/v0.1.0/`](legacy/v0.1.0/)。

### `0.2.0` — 从可运行工具到本地任务系统

2026 年 7 月，项目没有继续在原型上叠加功能，而是围绕任务语义、数据边界、产物交付和 Agent 体验完成了一次整体重建。

从这一版本开始，一次网络请求不再等同于一个 Job，本地等待到期不再被描述为任务失败，图片下载问题也不会推翻上游已经确认的成功。SQLite、显式状态机、多图片结果、受控 Artifact Store 和稳定 MCP 契约共同组成了新的可靠性边界。

这次重构继承了 `0.1.0` 已经验证的业务经验，但没有逐行迁移它的内部结构。重构过程中的产品、领域、存储和接口决策保存在 [`docs/rebuild/`](docs/rebuild/)。

### `0.2.1` — 让边界经得住真实使用

`0.2.1` 继续做的不是扩张功能数量，而是让已经建立的设计经受代码审阅、真实 ModelScope 工作流和多个 stdio MCP Host 的检验。

这一阶段进一步收紧了取消与并发、数据库和文件提交、Provider 网络生命周期、列表隐私以及跨平台路径边界。它让系统不仅在理想流程中成立，也能在调用中断、畸形响应、部分成功和真实 Host 环境中保持一致。

这条演进路线的重点从来不是功能越来越多，而是系统对“哪些事实可以被相信”回答得越来越清楚。

完整版本变化和兼容边界见 [CHANGELOG.md](CHANGELOG.md)。

## 🧪 开发

常用质量门禁：

```bash
uv lock --check
uv sync --locked --all-groups
uv run ruff format --check
uv run ruff check
uv run ty check
uv run pytest
uv build --no-sources
```

默认测试不会访问 ModelScope。只有明确允许外部调用和额度消耗时才运行 live 测试：

```bash
MODELSCOPE_IMAGE_GEN_RUN_LIVE_TESTS=1 \
MODELSCOPE_SDK_TOKEN=replace-with-your-modelscope-token \
uv run pytest -m live
```

更完整的架构边界、变更路径和验证要求见[项目维护与交接手册](docs/maintenance/README.md)。

## 🙏 灵感来源与致谢

本项目受到 [`zym9863/modelscope-image-mcp`](https://github.com/zym9863/modelscope-image-mcp) 的启发。

原项目以简洁而实用的方式展示了如何通过 MCP 接入 ModelScope 图像生成，为这个方向提供了重要的起点。本仓库沿着这条路径，继续探索长耗时 Agent 工作流中的任务提交、状态观察、上下文恢复和本地产物交付，并逐步补充了持久化 Job、多图片结果、结构化工具契约与安全落盘等能力。

感谢原作者公开分享这一方向上的实践。正是这些可以被阅读、验证和继续思考的开源工作，让后续的整理、重构与延展成为可能。

也感谢 MCP、ModelScope、uv、HTTPX、Pydantic、SQLite、AnyIO 和 Pillow 社区提供的基础设施与持续工作。

## 📌 支持与许可

- 普通问题与缺陷：[GitHub Issues](https://github.com/NeutrinoY/modelscope-image-gen/issues)
- 安全问题与秘密泄漏：[SECURITY.md](SECURITY.md)
- 版本变化与升级边界：[CHANGELOG.md](CHANGELOG.md)
- 项目许可：[MIT License](LICENSE)
