# ModelScope Image Gen MCP 核心代码组织

## 文档状态

- 状态：已确认
- 前置文档：`00-rebuild-direction.md` 至 `05-mcp-interface-contract.md`
- 适用目标：重构后的 V1

本文定义 V1 的包结构、依赖方向、领域实现、应用用例、端口、基础设施适配器、MCP 适配器、composition root、CLI 和测试组织。目录可以在不改变职责的前提下做小幅机械调整，但禁止破坏本文中的层次与依赖规则。

## 1. 总体结构

```text
src/modelscope_image_gen/
├── __init__.py
├── __main__.py
├── cli.py
├── bootstrap.py
│
├── domain/
│   ├── ids.py
│   ├── states.py
│   ├── errors.py
│   ├── requests.py
│   ├── artifacts.py
│   └── jobs.py
│
├── application/
│   ├── results.py
│   ├── views.py
│   ├── next_steps.py
│   ├── queries.py
│   │
│   ├── ports/
│   │   ├── provider.py
│   │   ├── repository.py
│   │   ├── artifact_store.py
│   │   ├── clock.py
│   │   ├── identifiers.py
│   │   └── waiting.py
│   │
│   └── use_cases/
│       ├── submit_generation.py
│       ├── check_generation.py
│       ├── fetch_generation_result.py
│       ├── list_generations.py
│       └── generate_image.py
│
├── infrastructure/
│   ├── config/
│   │   ├── settings.py
│   │   └── paths.py
│   │
│   ├── modelscope/
│   │   ├── provider.py
│   │   ├── schemas.py
│   │   ├── mapping.py
│   │   └── error_mapping.py
│   │
│   ├── sqlite/
│   │   ├── connection.py
│   │   ├── repository.py
│   │   ├── row_mapping.py
│   │   └── migrations/
│   │       └── v001_initial.sql
│   │
│   ├── artifacts/
│   │   ├── store.py
│   │   ├── paths.py
│   │   └── image_validation.py
│   │
│   ├── concurrency/
│   │   └── job_locks.py
│   │
│   └── system/
│       ├── clock.py
│       ├── identifiers.py
│       └── waiting.py
│
└── mcp_adapter/
    ├── server.py
    ├── tool_contract.py
    ├── registry.py
    ├── mapping.py
    │
    ├── models/
    │   ├── common.py
    │   ├── inputs.py
    │   └── outputs.py
    │
    ├── handlers/
    │   ├── submit.py
    │   ├── check.py
    │   ├── fetch.py
    │   ├── list_jobs.py
    │   └── generate.py
    │
    └── presenters/
        ├── common.py
        ├── success.py
        └── errors.py
```

`mcp_adapter` 明确表达协议适配职责，避免把 MCP 当成整个项目的核心领域。

## 2. 依赖方向

```text
mcp_adapter ───────┐
                   ↓
              application
                   ↓
                domain
                   ↑
              application ports
                   ↑
infrastructure ────┘

bootstrap → 所有层，仅负责组装
cli       → bootstrap
```

硬约束：

- `domain` 不导入项目其他层。
- `application` 只导入 domain、application 自身和 application ports。
- `infrastructure` 实现 application ports，可以导入 domain/application port 类型。
- `mcp_adapter` 调用 application，不直接调用 infrastructure。
- `bootstrap` 是唯一允许同时认识协议、应用和具体基础设施实现的 composition root。
- `cli` 只调用 bootstrap，不创建 Repository、HTTP Client 或 ToolContract。
- 任意新代码都不得导入 `legacy/`。

## 3. Domain 层

Domain 只表达业务事实、不变量和状态转换。

实现方式：

- 使用标准库 `dataclass(frozen=True, slots=True)`。
- 枚举使用标准库 `StrEnum`。
- 集合对外使用不可变 tuple 语义。
- 状态变化返回新的值或聚合，不通过任意属性赋值破坏不变量。
- 领域模块不读取系统时间、随机数、环境变量或文件系统。
- 不使用 Pydantic、MCP、HTTPX、aiosqlite、platformdirs 或 Pillow。

聚合行为示例：

```text
GenerationJob.mark_submitted(...)
GenerationJob.observe_running(...)
GenerationJob.observe_success(...)
GenerationJob.observe_failure(...)

GeneratedImage.mark_available(...)
GeneratedImage.mark_failed(...)
```

应用层不能通过 `dataclasses.replace()` 任意绕过聚合方法拼装非法状态。若确实需要内部重建，使用明确的 Repository rehydration factory，并在创建后验证全部不变量。

### 3.1 Domain 模块职责

- `ids.py`：JobId、ImageId、ArtifactKey 等值对象。
- `states.py`：JobStatus、ArtifactStatus、聚合产物状态派生。
- `errors.py`：DomainError、ErrorCode、ErrorStage、ErrorCategory。
- `requests.py`：GenerationRequest、ImageSize。
- `artifacts.py`：ProviderImageReference、GeneratedImage、LocalArtifact。
- `jobs.py`：GenerationJob 聚合与状态转换。

`domain/__init__.py` 不批量重导出整个领域表面，避免循环导入和隐式公共 API。

## 4. Application 层

Application 负责业务用例编排、事务边界外的步骤顺序、端口调用、取消和下一步派生。

它不负责：

- MCP wire 类型。
- HTTP 请求格式。
- SQLite SQL。
- Pillow 图片解析。
- 操作系统路径解析。
- 日志输出格式。

### 4.1 五个用例

```text
SubmitGeneration
CheckGeneration
FetchGenerationResult
ListGenerations
GenerateImage
```

每个用例：

- 构造函数显式注入依赖。
- 只暴露一个清晰的 `execute()`。
- 返回 application result。
- 不读取全局 Settings。
- 不创建 HTTP Client 或数据库连接。
- 不吞掉取消异常。
- 不依赖 MCP context。

`GenerateImage` 组合 submit/check/fetch 用例，不复制实现。

禁止重建一个同时负责全部行为的 `ImageGenerationService`，也禁止通过 Mixin 和隐式 `self` 属性重新制造同一问题。

## 5. Application Result

Application 使用标准库不可变泛型结果：

```text
OperationResult[T]
├── ok: bool
├── data: T | None
└── error: ApplicationError | None
```

它与 MCP ToolEnvelope 语义相近，但不是同一个类型。

理由：

- Application 不依赖 Pydantic 或 `CallToolResult`。
- CLI、测试和未来其他适配器可复用用例。
- MCP adapter 显式将 OperationResult 转成 concrete ToolOutput。
- 应用错误可以包含当前 Job 等恢复上下文，而不承担 wire schema。

ApplicationResult 自身验证 ok/data/error 不变量。

## 6. Application Views

`application/views.py` 定义适配器无关的只读视图：

- JobView。
- JobSummaryView。
- GeneratedImageView。
- ListPage。
- FetchOutcome。
- GenerateOutcome。

这些使用标准库 dataclass，不使用 Pydantic，也不包含：

- MCP 工具名称。
- CallToolResult。
- SQLite row/revision。
- httpx response。
- 绝对路径以外的基础设施私有对象。

绝对产物路径属于应用可消费视图，可以由 ArtifactStore 解析后进入完整结果；领域和数据库仍只保存相对路径。

## 7. NextStep

Application 使用：

```text
NextStep
├── kind: CHECK | FETCH
├── job_id
└── recommended_wait_seconds
```

它不保存 MCP 工具名称。

MCP adapter 映射：

```text
CHECK → check_image_generation
FETCH → fetch_image_generation_result
```

NextStep 派生逻辑集中在 application 层的单一策略函数中，五个用例不得分别实现略有差异的 next action 判断。

## 8. Ports

Application ports 使用 `typing.Protocol` 定义。Protocol 只表达项目真正需要的最小能力，不直接镜像第三方库 API。

### 8.1 ImageGenerationProvider

```text
ImageGenerationProvider
├── submit(request)
├── check(provider_task)
└── open_image(provider_image_reference)
```

职责：

- `submit` 返回类型化 Provider submission outcome。
- `check` 返回封闭 Provider status union。
- `open_image` 返回异步上下文管理的字节流。
- 管理全部外部网络访问和 HTTP response 生命周期。

Provider 不：

- 保存本地文件。
- 访问 SQLite。
- 生成 MCP DTO。
- 决定 Job 状态转换。
- 动态发现插件。

调用模式：

```python
async with provider.open_image(reference) as stream:
    artifact_store.save(..., stream)
```

Application 只看到通用异步字节流，不看到 `httpx.Response`。

### 8.2 GenerationJobRepository

```text
GenerationJobRepository
├── add(job)
├── get(job_id)
├── save(job, expected_revision)
├── list(query)
├── recover_stale_submitting(...)
├── find_expired_terminal(...)
└── schedule_cleanup(...)
```

Repository 返回：

```text
StoredJob
├── job: GenerationJob
└── revision: int
```

revision 是 application persistence value，不进入领域聚合。

列表查询返回摘要投影，不为了显示一页任务加载所有 prompt、Provider locator 和图片详情。

SQLite cursor、row、connection 和 SQL 不越过端口。

### 8.3 ArtifactStore

```text
ArtifactStore
├── save(job_id, image, stream)
├── inspect_existing(job_id, image)
├── resolve_path(local_artifact)
├── clean_temporary_files(...)
└── delete_job_artifacts(...)
```

职责：

- 路径边界。
- 临时文件。
- 字节上限。
- SHA-256。
- Pillow 验证。
- 像素上限。
- 原子提交。
- 已有文件与元数据修复检测。

ArtifactStore 不：

- 下载远程 URL。
- 更新 Job 或 SQLite。
- 生成 MCP DTO。
- 解析 ModelScope response。

### 8.4 Clock、Identifiers、Waiting

```text
Clock.now()
IdentifierFactory.new_job_id()
IdentifierFactory.new_image_id()
Waiter.sleep(seconds)
```

这些端口用于：

- 生成稳定时间和 UUIDv7。
- 无真实睡眠地测试 generate 编排。
- 避免 monkeypatch 全局系统函数。

## 9. Provider Outcome 类型

Provider port 返回 application 可理解的封闭结果类型，而不是 `dict[str, Any]` 或任意异常字符串。

概念类型：

```text
ProviderSubmission
ProviderPending
ProviderRunning
ProviderSucceeded
ProviderFailed
ProviderUnknownStatus
ProviderFailure
```

ProviderFailure 在 infrastructure 边界完成：

- HTTP 状态分类。
- Retry-After 解析。
- request ID 提取。
- 敏感信息净化。
- retryable 判断。

Application 负责把 Provider outcome 应用到领域聚合。

## 10. ModelScope 适配器

### 10.1 schemas.py

使用私有 Pydantic model 严格解析：

- SubmitResponse。
- StatusResponse。
- ProviderErrorResponse。
- 图片引用结构。

配置 `extra` 策略必须经过真实 fixture 决定。影响控制流的字段严格验证；无关新增字段可以忽略，避免上游添加非关键字段导致整体中断。

### 10.2 mapping.py

- ModelScope 状态字符串映射为 Provider outcome union。
- 图片引用映射为 ProviderImageReference。
- 不包含 HTTP 调用。
- 未知状态显式返回 ProviderUnknownStatus。

### 10.3 error_mapping.py

集中处理：

- HTTP status。
- request/network errors。
- Retry-After。
- request ID。
- 上游安全正文摘要。
- retryable 分类。

禁止在 submit/check/open_image 中分别复制错误分类表。

### 10.4 provider.py

- 组装 URL、Header 和 payload。
- 使用 lifespan 注入的 `httpx.AsyncClient`。
- 调用 schema/mapping/error mapping。
- 不保存 Job 或图片文件。

## 11. SQLite 适配器

### 11.1 connection.py

- 打开/关闭 aiosqlite connection。
- 应用 PRAGMA。
- 提供窄事务 helper。
- 读取和更新 schema version。

### 11.2 migrations

迁移使用 package 内 `.sql` 文件，通过 `importlib.resources` 读取。

要求：

- 文件名包含顺序版本。
- 每个文件负责一个迁移。
- wheel 测试验证 migration 文件被打包。
- SQL 文件不包含业务状态转换逻辑。

### 11.3 row_mapping.py

- SQLite row → 领域值/聚合。
- 领域聚合 → SQL 参数。
- 验证持久化数据不变量。
- 不执行查询或事务。

### 11.4 repository.py

- 实现 GenerationJobRepository。
- 管理事务、查询、revision 和 pagination。
- 调用 row mapping。
- 不包含 ModelScope 或 MCP 逻辑。

禁止把 migration、连接管理、SQL、row mapping 和领域状态机重新放进单个 Repository 大文件。

## 12. Artifact 适配器

### 12.1 paths.py

- 生成 ArtifactKey 和受控相对路径。
- 处理 Windows/Posix 路径边界。
- 检测绝对路径、遍历、符号链接和重解析点逃逸。

### 12.2 image_validation.py

- 使用 Pillow 验证图片。
- 应用像素上限。
- 返回实际格式、媒体类型和尺寸。
- 不决定最终路径或写数据库。

### 12.3 store.py

- 流式写入临时文件。
- 应用字节上限和 SHA-256。
- 调用 image validation。
- 原子提交最终文件。
- 检测并修复已存在的有效产物。
- 清理自己创建的失败临时文件。

## 13. JobLockManager

`infrastructure/concurrency/job_locks.py` 实现进程内 keyed AnyIO lock。

要求：

- 同一 Job check/fetch 串行。
- 不同 Job 不互相阻塞。
- lock 条目引用计数或等价生命周期管理，避免无界增长。
- 调用取消时正确释放锁。
- 不承担跨进程协调。

Application 依赖一个窄 `JobLock` port 或通过用例装饰器使用锁，不能直接导入具体 lock registry。

## 14. MCP Adapter

### 14.1 models

只包含 MCP wire Pydantic DTO：

- input models。
- concrete output envelope。
- ErrorOutput、JobOutput、GeneratedImageOutput。
- NextActionOutput。

这些模型不进入 application/domain。

### 14.2 handlers

每个 handler 执行：

```text
Pydantic input
→ application command/query
→ use case
→ application result
→ MCP mapping
```

handler 不写 SQL、HTTP、文件或状态转换规则。

### 14.3 mapping.py

- Application view/result → MCP DTO。
- NextStep kind → MCP tool name。
- Domain/Application error → ErrorOutput。
- Artifact path → allowed wire path。

### 14.4 presenters

只生成 TextContent 文本：

- 成功摘要。
- 等待摘要。
- 部分成功摘要。
- 安全错误摘要。
- 列表页模型摘要。

Presenter 不改变 structured content，不重新判断业务状态，也不读取 Infrastructure。

### 14.5 registry.py

按固定顺序注册五个 ToolContract：

```text
submit_image_generation
check_image_generation
fetch_image_generation_result
list_image_generations
generate_image
```

registry 是只读映射。未知工具通过 MCP protocol error 返回，不进入任何业务 handler。

### 14.6 server.py

- 创建低层 MCP Server。
- 连接 list_tools/call_tool 到 registry。
- 声明 Tools-only capability。
- 不创建具体基础设施资源。

## 15. Bootstrap 与 Lifespan

`bootstrap.py` 是 composition root。

启动组装：

```text
Settings
→ 路径与 logging
→ HTTPX AsyncClient
→ ModelScope Provider
→ SQLite connection/repository
→ Artifact Store
→ Clock / IdentifierFactory / Waiter
→ JobLockManager
→ Use Cases
→ ToolContracts
→ Low-level MCP Server
```

Lifespan context：

```text
AppContext
├── use_cases
├── repository
├── maintenance
└── application_metadata
```

MCP handlers 主要访问 use cases，不随意取得底层 HTTP Client、SQLite connection 或 ArtifactStore 实现。

关闭顺序与创建顺序相反。任何资源创建中途失败时，已经创建的资源通过 AsyncExitStack 或等价机制正确释放。

模块 import 阶段不读取 Settings、不打开数据库、不创建 Client、不运行迁移。

## 16. UseCases 容器

允许定义不可变：

```text
UseCases
├── submit
├── check
├── fetch
├── list_jobs
└── generate
```

它只是依赖集合，不包含转发方法、共享可变状态或业务逻辑。不得演变为新的 Service facade。

## 17. CLI 与入口

`cli.py` 负责：

- 最小 CLI 参数，例如 `--version`。
- 配置 stderr logging。
- 调用 bootstrap。
- 启动 stdio Server。
- 将启动配置错误输出为清晰 stderr，并返回非零退出码。

`__main__.py` 只调用 `cli.main()`。

`pyproject.toml` console script 指向 package CLI。根目录不保留 `main.py`。

`__init__.py` 保持轻量，不导入 Server 或创建全局资源；可以只暴露包版本读取 helper 或完全为空。

## 18. 测试组织

```text
tests/
├── unit/
│   ├── domain/
│   └── application/
├── integration/
│   ├── modelscope/
│   ├── sqlite/
│   └── artifacts/
├── contract/
│   └── mcp/
├── e2e/
│   ├── stdio/
│   └── wheel/
├── live/
│   └── modelscope/
└── fixtures/
    ├── provider_responses/
    └── images/
```

规则：

- unit 测试无网络、真实数据库和真实文件持久化。
- integration 使用临时 SQLite/Artifact root 和 MockTransport。
- MCP contract 使用官方内存 Client。
- e2e stdio 使用真实 console script。
- wheel 测试从构建产物安装，验证 migration SQL/package data。
- live 默认跳过，只有显式环境标记和 Token 时运行。
- fixture 脱敏且说明来源契约，不保存 Token 或签名 URL。

## 19. 架构测试

使用标准库 AST 编写轻量 architecture test，不增加 import-linter。

测试至少保证：

- domain 不导入 Pydantic/MCP/HTTPX/SQLite/Pillow/platformdirs。
- application 不导入 mcp_adapter 或 infrastructure。
- mcp_adapter 不导入具体 infrastructure 模块。
- 新代码不导入 legacy。
- bootstrap 之外没有同时导入 MCP adapter 与具体 infrastructure 的模块。
- 模块 import 不执行明显资源创建入口。

AST 测试是依赖方向保护，不试图替代 ty 或 Ruff。

## 20. 文件规模与命名

- 每个模块只有一个稳定职责。
- 不设置机械硬行数上限，但超过约 300 行时必须检查是否混合职责。
- 不创建只有转发作用的历史兼容模块。
- 不用 `utils.py`、`helpers.py` 承载无归属逻辑；使用具体职责名称。
- 不通过 `__init__.py` 大规模重导出掩盖真实依赖。
- 不使用 `service.py` 作为无法分类代码的容器。
- 共享逻辑优先放入明确领域行为、应用策略或具体基础设施组件。

## 21. 错误传播

- Domain 产生不变量和状态错误。
- Infrastructure 将第三方异常净化为 Provider/Repository/Artifact failure。
- Application 将失败组织为 OperationResult 和恢复上下文。
- MCP adapter 映射为 ToolEnvelope、TextContent 和 is_error。
- 未预期异常只在边界记录详细内部日志；wire 返回稳定 INTERNAL_ERROR。

预期失败不通过任意 `except Exception` 猜测业务语义。取消、KeyboardInterrupt 和系统退出不包装成普通工具错误。

## 22. 验收标准

至少验证：

1. Domain 可以在没有任何第三方依赖的测试中导入和运行。
2. 每个 use case 可以用内存端口替身独立测试。
3. GenerateImage 复用 submit/check/fetch，不包含重复 Provider 调用逻辑。
4. Provider port 不泄露 httpx 类型。
5. Repository port 不泄露 aiosqlite/row 类型。
6. ArtifactStore port 不承担网络或数据库职责。
7. MCP handler 不直接导入具体 Infrastructure。
8. ToolContract registry 固定注册五个工具。
9. Bootstrap 是唯一 composition root。
10. CLI import 不触发配置解析或资源创建。
11. migration SQL 存在于 wheel。
12. architecture test 拦截跨层违规导入。
13. Job lock 在取消后释放并清理 registry 条目。
14. live 测试默认跳过且 fixture 完全脱敏。

## 23. 后续文档约束

- `07-agent-experience.md` 只能改变描述、文本呈现和文档体验，不能把业务逻辑移入 presenter。
- `08-implementation-brief.md` 必须按本文的依赖方向和测试层次安排实现顺序。
- 第一条竖切应穿过 domain → application → infrastructure → mcp_adapter，但每层只实现 submit 所需最小能力。
- 后续能力通过新增/扩展 use case 和适配器实现，不重建中央 Service。
