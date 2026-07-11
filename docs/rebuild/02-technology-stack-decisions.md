# ModelScope Image Gen MCP 技术栈决策

## 文档状态

- 状态：已确认
- 前置文档：`00-rebuild-direction.md`、`01-product-and-information-architecture.md`
- 适用目标：重构后的 V1

本文锁定 V1 的运行时、MCP SDK、异步模型、持久化、图片处理、构建、质量工具、测试和版本策略。后续实现不得在没有修订本文的情况下引入重复工具链、替代框架或超出 V1 需要的基础设施。

## 1. 选型原则

技术选择必须服务于已经确认的产品语义：

- 长任务可恢复。
- 本地任务可发现。
- 一次任务支持 `list[GeneratedImage]`。
- 图片需要下载、验证并安全落盘。
- MCP 工具需要清晰、稳定、可测试。
- 项目需要通过 PyPI/`uvx` 分发。
- Windows 和 Linux 都是正式支持平台。

选型优先级：

```text
语义正确性
> 稳定性与安全性
> 类型与测试能力
> 维护成本
> 性能
> 新颖程度
```

“现代”不等于无条件采用最新预发布版本。预发布组件只有在与目标架构直接相关、风险明确且版本被精确固定时才允许使用。

## 2. Python 运行时

V1 使用 Python 3.14 的标准 GIL 构建。

```toml
[project]
requires-python = ">=3.14,<3.15"
```

项目根目录使用：

```text
.python-version = 3.14
```

决策理由：

- Python 3.14 已进入稳定维护阶段。
- 项目是可执行 MCP 服务，不是需要覆盖多个旧运行时的通用基础库。
- 明确上限可以让发布元数据诚实反映已测试范围。
- uv 可以为 `uvx` 和本地开发管理目标解释器。

禁止事项：

- V1 不支持 Python 3.13 及以下版本。
- V1 不使用 `3.14t` free-threaded 构建。
- 不为了旧 Python 兼容保留 `from __future__ import annotations` 的项目级模板要求。
- 未经 CI 和依赖验证，不提前声明 Python 3.15 支持。

## 3. uv 与构建后端

uv 统一负责：

- Python 版本管理。
- 虚拟环境。
- 依赖声明与解析。
- 跨平台锁文件。
- 开发工具执行。
- 构建和发布。

版本要求：

```toml
[tool.uv]
required-version = ">=0.11.28,<0.12"
```

构建后端使用 `uv_build`：

```toml
[build-system]
requires = ["uv_build>=0.11.28,<0.12"]
build-backend = "uv_build"
```

项目采用 `src/` package layout，并提交 `uv.lock`。

禁止事项：

- 不同时维护 requirements 文件作为第二依赖事实来源。
- 不使用 Poetry、PDM 或 Hatch 管理项目环境。
- 不继续使用 Hatchling 构建当前简单纯 Python 包。
- `uv.lock` 不手工编辑。
- `legacy/` 不加入 uv workspace。

## 4. 版本来源

项目版本静态保存在 `pyproject.toml` 的 `[project].version` 中。

运行时通过：

```python
importlib.metadata.version("modelscope-image-gen-mcp")
```

获取版本，并用于 MCP server metadata、CLI 版本输出和诊断信息。

禁止在以下位置重复硬编码版本：

- Python 模块常量。
- MCP 初始化代码。
- `server.json` 生成逻辑。
- README 示例。

发布流程负责让发行元数据与项目版本一致。

## 5. MCP Python SDK v2

V1 明确以 MCP Python SDK v2.0 为目标，不实现 v1 兼容层。

开发期在 v2 尚未稳定时精确固定经过验证的 beta：

```toml
"mcp==2.0.0b1"
```

稳定版发布并完成回归后切换为：

```toml
"mcp>=2.0,<3"
```

beta 阶段必须：

- 允许解析 MCP 所需的预发布依赖。
- 额外约束其他依赖只使用稳定版本。
- MCP beta 升级必须单独提交并运行完整回归。
- 不在同一变更中同时升级 MCP、Pydantic 和领域接口。

### 5.1 MCP API 层级

V1 使用 MCP v2 低层 `Server`，由项目的强类型 ToolContract 适配层生成和验证工具契约。

该决策来自对 `mcp==2.0.0b1` 实际发布包的源码检查和内存 Client 实验，而不是继承旧项目做法。高层 `MCPServer` 无法同时自然满足已经确认的以下要求：

- 只声明 Tools capability，不声明未使用的 Prompts/Resources。
- 模型只接收简洁摘要，Host 接收完整 structured content。
- 工具失败拥有结构化 reason code 和正确 `is_error=true`。
- `tools/list` 同时公布明确 output schema。

低层 Server 只负责 MCP 协议接线。项目必须通过 Pydantic ToolContract 层：

- 从输入/输出模型生成 JSON Schema。
- 验证输入参数和 structured content。
- 注册工具名到应用 handler 的映射。
- 生成简洁 TextContent。
- 设置 `is_error` 和 ToolAnnotations。
- 统一净化意外异常。

禁止继承旧项目的手写 schema、大段 `if name == ...` 分发和重复参数验证。MCP 代码仍然只存在于适配层，并使用官方内存 Client 进行契约测试。

### 5.2 MCP CLI extra

运行时依赖使用普通 `mcp`。开发组使用相同版本的 `mcp[cli]`，提供 Inspector 和开发命令：

```toml
"mcp[cli]==2.0.0b1"
```

稳定后，运行时和开发组必须同步切换到同一个 v2 稳定版本范围。

## 6. 异步模型

项目使用 AnyIO 表达取消、等待、超时和任务组：

```toml
"anyio>=4.14,<5"
```

使用场景：

- 轮询等待。
- 阻塞式 `generate_image` 的最大等待时间。
- 工具取消传播。
- 并发下载多个 `GeneratedImage`。
- 需要结构化并发的短生命周期任务。

实际运行后端固定为 asyncio，以兼容 MCP SDK、HTTPX 和 aiosqlite 的目标组合。

边界：

- 应用工作流优先使用 AnyIO 的公开取消和超时原语。
- 基础设施适配器可以在其实现边界使用 asyncio 专属库。
- 不支持 Trio 作为 V1 运行后端。
- 不创建脱离请求生命周期、无法追踪的 `asyncio.create_task()` 后台任务。
- 上游异步任务由 ModelScope 执行，本地服务不通过常驻后台协程模拟任务队列。

## 7. HTTP 客户端

ModelScope Provider 使用 HTTPX：

```toml
"httpx>=0.28.1,<1"
```

必须遵守：

- `httpx.AsyncClient` 在 MCP lifespan 中创建并复用。
- 不为每次 Provider 调用创建新的 Client。
- 提交、查询和下载使用各自明确的 timeout 配置。
- 配置连接池上限和合理 keep-alive。
- 图片下载使用流式读取和字节上限。
- 非 2xx 响应在 Provider 边界转换为上游错误。
- 尊重合法 `Retry-After` 信息。
- 只对明确可重试的阶段和错误执行有限重试。
- 不自动重试可能重复创建上游任务的提交请求，除非 ModelScope 提供可靠幂等键契约。

不引入 Tenacity。重试行为是业务和上游契约的一部分，由 Provider 中的小型显式策略实现。

## 8. 配置

使用 Pydantic 与 pydantic-settings：

```toml
"pydantic>=2.13.4,<2.14"
"pydantic-settings>=2.14,<3"
```

beta 阶段限制 Pydantic `<2.14`，防止启用预发布解析后意外选择 Pydantic alpha。MCP v2 稳定且移除全局预发布需求后，可重新评估为 `<3`。

配置边界：

- pydantic-settings 只用于进程配置。
- API Token 使用 `SecretStr`。
- 配置在启动阶段完成校验。
- 领域层不依赖 BaseSettings。
- MCP 工具参数不是服务器配置渠道。
- `.env` 只作为本地开发便利，不是部署契约。
- MCP Host 正式配置通过环境变量传入。

不引入第二套配置框架，也不直接使用 python-dotenv API。

## 9. 持久化

V1 使用 SQLite 作为本地任务和产物元数据的事实来源，并通过 aiosqlite 访问：

```toml
"aiosqlite>=0.22,<1"
```

选择 SQLite 的原因：

- 支持服务重启恢复。
- 支持 `list_image_generations` 的过滤、排序和分页。
- 支持一个 Job 对应多个图片记录。
- 支持事务和幂等更新。
- 支持 schema 版本与迁移。
- 不需要外部数据库服务。

明确不使用：

- 每任务一个 JSON 文件。
- SQLAlchemy。
- ORM。
- 外部 PostgreSQL、Redis 或消息队列。

工程边界：

- 领域对象不是数据库记录对象。
- 应用层依赖 Repository 端口。
- SQLite 适配器负责 schema、事务和行映射。
- 不让 SQL 或 aiosqlite 类型越过基础设施边界。
- 数据库迁移必须显式、可测试，不能依赖运行时隐式猜测旧结构。

精确 schema、索引、事务和保留策略由 `04-config-and-storage-schema.md` 定义。

## 10. 本地目录

使用 platformdirs 管理操作系统标准目录：

```toml
"platformdirs>=4,<5"
```

它用于解析默认的：

- 应用数据目录。
- SQLite 数据库目录。
- 缓存目录。
- 日志目录（如果启用文件日志）。

图片 artifact root 允许由操作者配置，但默认值必须稳定，不能因为 MCP Host 的启动工作目录变化而改变。

所有最终目录在配置层解析并传入基础设施；领域和应用层不得直接调用 platformdirs。

## 11. 图片验证与保存

使用 Pillow：

```toml
"Pillow>=12.3,<13"
```

Pillow 的 V1 职责：

- 验证下载内容确实是可解码图片。
- 获取规范化格式、媒体类型、宽度和高度。
- 应用像素数量和异常资源限制。
- 拒绝损坏、伪装或不受支持的图片内容。

默认保存策略：

1. 流式下载到 artifact root 内的临时文件。
2. 限制最大下载字节数。
3. 使用 Pillow 验证临时文件。
4. 提取图片元数据。
5. 关闭图片对象。
6. 将原始下载字节原子移动到最终路径。

默认不重新编码图片，避免质量变化、元数据丢失和额外 CPU 消耗。只有未来明确提供格式转换能力时才允许重编码，并需要独立产品与接口决策。

Pillow 不进入领域层；图片验证和文件提交属于 Artifact Store 适配器职责。

## 12. 标识与时间

优先使用 Python 3.14 标准库：

- 本地 Job ID 使用 UUIDv7。
- 图片 ID 使用独立 UUIDv7，不能用列表索引充当长期标识。
- 持久化时间统一使用带 UTC 时区的 `datetime`。
- 对外使用 RFC 3339/ISO 8601 兼容字符串。
- 测试通过注入 Clock 端口控制时间，不引入 freezegun。

ModelScope Task ID 作为上游标识独立保存，不替代本地 Job ID。

## 13. 日志与可观测性

使用 Python 标准库 logging，不引入 structlog 或 loguru。

要求：

- stdio 模式日志只写 stderr 或明确配置的文件。
- 不使用 `print()` 输出诊断信息。
- 日志使用稳定事件名和键值上下文。
- 默认记录本地 Job ID、阶段、耗时和脱敏请求 ID。
- 默认不记录完整 prompt、Token、Authorization Header 或签名 URL。
- 异常日志在边界净化敏感信息。

V1 不引入完整 OpenTelemetry SDK 或远程遥测后端。未来远程部署需要可观测性时单独决策。

## 14. 类型检查

ty 是 V1 唯一类型检查器，替代 Pyright 和 mypy。

beta 阶段精确固定：

```toml
"ty==0.0.58"
```

策略：

- CI 中 `ty check` 是阻断门禁。
- ty 升级使用独立提交。
- 升级前后比较诊断变化。
- 不通过大范围 `# type: ignore` 消除新诊断。
- 第三方类型缺陷优先通过窄边界适配、stub 或有说明的局部抑制处理。
- 不同时运行 Pyright 或 mypy 形成冲突事实来源。

ty 稳定后再调整版本范围；在 `0.0.x` 阶段不使用宽泛下限。

## 15. 格式化与 Lint

Ruff 统一负责格式化、导入排序和 Lint：

```toml
"ruff>=0.14,<0.15"
```

CI 执行：

```text
ruff format --check
ruff check
```

不引入：

- Black。
- isort。
- Flake8。
- 独立 import sorter。
- 与 Ruff 重复的格式化或基础 Lint 工具。

Ruff 目标版本设置为 Python 3.14。规则集以正确性、现代化、bug 风险和类型友好为主，具体配置在新 `pyproject.toml` 中落实。

## 16. 测试

测试框架使用 pytest：

```toml
"pytest>=9,<10"
"pytest-cov"
```

异步测试使用 AnyIO pytest plugin：

```python
@pytest.mark.anyio
```

测试后端固定为 asyncio。

不引入 pytest-asyncio，避免同一项目存在两套异步测试生命周期。

测试层次：

1. 领域状态机和错误模型单元测试。
2. 应用用例测试，使用内存端口替身。
3. ModelScope Provider 测试，使用 `httpx.MockTransport` 和脱敏 fixture。
4. SQLite Repository 事务、迁移、分页和重启恢复测试。
5. Artifact Store 下载限制、图片验证、原子保存和路径边界测试。
6. MCP v2 内存 Client 契约测试。
7. stdio 子进程冒烟测试。
8. 需要显式 Token 才运行的真实 ModelScope 集成测试。
9. wheel 安装与命令入口测试。

V1 暂不引入 respx；只有 `httpx.MockTransport` 明显无法保持测试可读性时才重新评估。

## 17. 开发依赖组

beta 开发阶段建议：

```toml
[dependency-groups]
dev = [
    "mcp[cli]==2.0.0b1",
    "pytest>=9,<10",
    "pytest-cov",
    "ruff>=0.14,<0.15",
    "ty==0.0.58",
]
```

不引入 pre-commit。开发命令和 CI 都通过 uv 执行同一组工具，避免额外钩子环境与项目锁文件漂移。未来团队协作证明需要本地 Git hook 时再单独决定。

## 18. 完整运行时依赖

MCP v2 beta 阶段的目标运行时依赖：

```toml
dependencies = [
    "mcp==2.0.0b1",
    "anyio>=4.14,<5",
    "httpx>=0.28.1,<1",
    "pydantic>=2.13.4,<2.14",
    "pydantic-settings>=2.14,<3",
    "aiosqlite>=0.22,<1",
    "platformdirs>=4,<5",
    "Pillow>=12.3,<13",
]
```

`uv.lock` 记录实际解析的精确版本。`pyproject.toml` 表达经过确认的兼容范围，不能用锁文件替代直接依赖声明。

## 19. CI 平台与门禁

正式 CI 至少覆盖：

- Windows + Python 3.14。
- Ubuntu + Python 3.14。

每次 Pull Request 执行：

```text
uv lock --check
uv sync --locked --all-groups
ruff format --check
ruff check
ty check
pytest
uv build --no-sources
安装 wheel 并执行 CLI/stdio 冒烟测试
```

Windows 是正式门禁，因为项目涉及：

- 文件名和路径规范化。
- 原子替换语义。
- MCP Host 本地启动。
- SQLite 文件行为。

macOS 在 V1 中属于尽力兼容平台，不进入首阶段阻断矩阵；发布前可以增加非阻断冒烟任务。

## 20. 发布与供应链

发布前必须：

- 使用 `uv build --no-sources` 构建。
- 验证 sdist 和 wheel 内容不包含 `legacy/`、Token、`.env`、任务数据库或生成图片。
- 从 wheel 安装并运行测试命令入口。
- 补齐 MIT `LICENSE` 和 PEP 621 项目元数据。
- 通过 GitHub Actions Trusted Publishing 发布 PyPI，避免长期 PyPI Token。
- 生成并校验 MCP Registry `server.json`。
- 保持 PyPI 包版本、MCP server 版本和 Registry 版本一致。

MCP Registry 当前仍属于独立发布契约，不影响第一条核心竖切实现。

## 21. 明确不采用

V1 明确不采用：

- MCP v1 API 或双版本实现。
- 高层 `MCPServer` 作为 V1 工具服务实现方式。
- 绕过 ToolContract 直接裸用低层 Server、手写 schema 或长条件分发。
- Trio 运行后端。
- 每任务 JSON 文件存储。
- SQLAlchemy 或其他 ORM。
- Redis、PostgreSQL 或消息队列。
- Tenacity。
- orjson。
- structlog 或 loguru。
- Pyright 或 mypy。
- pytest-asyncio。
- Black、isort 或 Flake8。
- respx。
- pre-commit。
- 完整 OpenTelemetry SDK。
- Docker 作为本地 stdio 分发的必要条件。

这些不是永久禁止项；只有后续产品需求提供明确理由并修订本文后才允许引入。

## 22. 验收标准

技术栈阶段完成时必须满足：

- uv 能在 Windows 和 Ubuntu 上解析并同步 Python 3.14 环境。
- MCP v2 beta 依赖不会导致 Pydantic 等无关依赖进入预发布版本。
- `uv.lock` 与 `pyproject.toml` 一致。
- 低层 `Server` 能通过 ToolContract 注册表和内存 Client 调用至少一个最小工具，并只声明 Tools capability。
- lifespan 能创建并释放 HTTP Client、SQLite Repository 和 Artifact Store。
- AnyIO 取消能够停止阻塞等待和并发图片下载。
- SQLite 能在进程重启后恢复任务。
- Pillow 能验证图片并在不重新编码的情况下保存原始字节。
- Ruff、ty、pytest 和构建全部通过。
- wheel 不包含 legacy 或运行时产物。

## 23. 后续文档约束

- `03-domain-model-and-behavior-map.md` 不得让领域对象依赖本文件中的具体基础设施库。
- `04-config-and-storage-schema.md` 负责定义 SQLite schema、迁移、目录、保留和清理策略。
- `05-mcp-interface-contract.md` 使用低层 `Server` 精确表达已确认的 Tools-only、结构化错误和双通道输出契约；所有 schema 必须由 Pydantic ToolContract 生成和验证。
- `06-core-organization.md` 必须维持 MCP、应用、领域和基础设施的单向依赖。
- `08-implementation-brief.md` 必须包含 Windows/Ubuntu CI、wheel 冒烟测试和真实 ModelScope 验证。
