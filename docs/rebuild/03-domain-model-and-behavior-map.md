# ModelScope Image Gen MCP 领域模型与旧行为映射

## 文档状态

- 状态：已确认
- 前置文档：`00-rebuild-direction.md`、`01-product-and-information-architecture.md`、`02-technology-stack-decisions.md`
- 适用目标：重构后的 V1

本文定义 V1 的领域对象、值对象、状态机、错误模型、部分成功语义和旧行为映射。SQLite schema、Pydantic DTO、MCP schema 和 ModelScope 原始响应都只能映射本文，不能反向塑造本文中的领域模型。

## 1. 领域原则

- 本地 Job 是本系统任务事实来源。
- ModelScope Task 是 Job 关联的外部执行记录。
- 上游生成成功与本地产物可用是不同事实。
- 一次任务的结果始终建模为有序的 `list[GeneratedImage]`。
- 网络、存储和 MCP 只是领域边界外的实现细节。
- 状态转换必须显式，不能由零散布尔字段隐式组合。
- 暂时性操作失败不能伪装成任务终态。
- 对 Agent 有意义的稳定错误必须在基础设施边界完成净化。

## 2. 聚合边界

`GenerationJob` 是 V1 的聚合根。

聚合包含：

```text
GenerationJob
├── GenerationRequest
├── ProviderTaskReference | None
├── list[GeneratedImage]
│   └── LocalArtifact | None
└── DomainError | None
```

所有 Job 状态变化、图片集合替换、图片产物状态变化和当前错误变化必须通过聚合行为完成。Repository 每次保存和读取完整一致的聚合快照；数据库行不是领域对象。

## 3. GenerationRequest

`GenerationRequest` 表达用户要求上游生成什么。

字段：

```text
prompt: str
model: str
size: ImageSize
negative_prompt: str | None
seed: int | None
```

约束：

- `prompt` 去除首尾空白后必须非空。
- `model` 去除首尾空白后必须非空。
- `negative_prompt` 保留用户语义；空字符串在边界规范化为 `None`。
- `seed` 的上游有效范围由 ModelScope Provider 校验。
- `size` 的基础正数约束属于值对象；模型特定范围由 Provider 校验。

不属于 `GenerationRequest`：

- 输出目录。
- 输出文件名。
- Job ID 或 Provider Task ID。
- HTTP timeout。
- 轮询次数或退避配置。
- 数据保留策略。
- 下载和图片验证设置。
- MCP Host 或调用方信息。

prompt 是敏感业务数据。领域对象可以持有它以表达任务语义，但持久化、列表返回、日志和清理策略由后续文档决定。

## 4. ImageSize

`ImageSize` 是不可变值对象：

```text
width: int
height: int
```

基础约束：

- 宽高必须为正整数。
- 值对象不解析 `WIDTHxHEIGHT` 字符串。
- 值对象不包含 ModelScope 或某个模型的最大最小尺寸规则。

字符串解析属于 MCP/应用输入边界。Provider 在提交前执行模型特定能力校验。

## 5. GenerationJob

`GenerationJob` 是本地任务事实来源。

字段：

```text
job_id: JobId
request: GenerationRequest
status: JobStatus
provider_task: ProviderTaskReference | None
images: tuple[GeneratedImage, ...]
last_error: DomainError | None
created_at: datetime
updated_at: datetime
submitted_at: datetime | None
completed_at: datetime | None
```

领域约束：

- `job_id` 是 UUIDv7 值对象。
- `images` 保持上游结果顺序，领域内部使用不可变序列语义。
- `provider_task` 只有成功获得上游 Task ID 后才存在。
- `submitted_at` 只有进入 `submitted` 后才存在。
- `completed_at` 只有 Job 进入 `succeeded` 或 `failed` 时才存在。
- `succeeded` 必须至少包含一个 `GeneratedImage`。
- `submitting` 不得包含 Provider Task ID 或图片。
- `submitted` 和 `in_progress` 必须包含 Provider Task ID，且不得包含图片。
- `failed` 可以没有 Provider Task ID，例如提交结果不确定。
- Job 成功后，图片下载或保存失败不能改变 Job 状态。

## 6. JobId 与 ImageId

`JobId` 和 `ImageId` 是不同的 UUIDv7 值对象。

规则：

- ID 在应用层创建，通过端口注入，领域行为不直接读取系统随机源。
- Provider Task ID 不得复用为 Job ID。
- 图片列表位置不得复用为 Image ID。
- ID 字符串格式必须稳定，但领域不承担 MCP 参数解析错误信息。

## 7. ProviderTaskReference

`ProviderTaskReference` 表达 Job 关联的上游执行记录。

字段：

```text
provider: ProviderName
task_id: str
request_id: str | None
last_provider_status: str | None
```

规则：

- V1 的 `provider` 固定表达 ModelScope，但仍使用显式值而不是隐含常量。
- `task_id` 必须非空。
- `request_id` 是脱敏诊断引用，不是 Job 身份。
- `last_provider_status` 只用于诊断和 API 漂移分析，不驱动 Agent 控制流。
- Provider 原始 JSON 不进入该对象。

## 8. JobStatus

V1 Job 状态：

```text
submitting
submitted
in_progress
succeeded
failed
```

含义：

- `submitting`：本地 Job 已持久化，正在创建上游任务，尚未获得可靠 Task ID。
- `submitted`：ModelScope 已接受任务并返回可追踪 Task ID。
- `in_progress`：ModelScope 明确报告排队或处理状态。
- `succeeded`：ModelScope 明确报告成功并返回至少一个图片引用。
- `failed`：ModelScope 明确报告失败，或出现不可恢复的提交/上游结果契约失败。

`timeout` 不是 JobStatus。它只能是某次操作的错误类别。

## 9. Job 状态转换

允许的状态转换：

```text
submitting
    ├── submitted
    └── failed

submitted
    ├── submitted
    ├── in_progress
    ├── succeeded
    └── failed

in_progress
    ├── in_progress
    ├── succeeded
    └── failed

succeeded ──> succeeded
failed    ──> failed
```

同状态转换允许更新上游诊断、时间和当前错误，但不能违反状态不变量。

禁止转换：

- `succeeded → failed`。
- `failed → submitted/in_progress/succeeded`。
- `submitted/in_progress → submitting`。
- 网络或调用超时直接导致 `submitted/in_progress → failed`。
- 未知上游状态直接导致 `submitted/in_progress → failed`。
- 本地图片失败导致任何 Job 状态变化。

非法转换产生稳定 `INVALID_JOB_TRANSITION` 领域错误，不静默忽略。

## 10. 提交时序

正确提交流程：

```text
校验 GenerationRequest
    ↓
创建 GenerationJob(status=submitting)
    ↓
持久化 Job
    ↓
调用 ModelScope submit
    ↓
获得 Task ID
    ↓
写入 ProviderTaskReference
    ↓
转换为 submitted 并持久化
```

该顺序保证外部副作用开始前存在本地提交意图记录。

### 10.1 提交前失败

输入校验或启动配置失败发生在 Job 创建前：

- 不创建 Job。
- 不调用 ModelScope。
- 返回调用级错误。

### 10.2 明确提交失败

ModelScope 明确拒绝且可确认没有创建任务：

- Job 转为 `failed`。
- 保存稳定提交错误。
- `possibly_submitted=false`。
- Agent 可以根据 `retryable` 决定是否重新提交新 Job。

### 10.3 提交结果不确定

请求可能已到达 ModelScope，但本地没有获得可靠 Task ID，例如读取响应前连接中断：

- Job 转为 `failed`。
- reason code 为 `SUBMISSION_OUTCOME_UNKNOWN`。
- `possibly_submitted=true`。
- 不自动重试。
- 错误明确说明重新提交可能创建重复任务。
- 有脱敏 Provider Request ID 时保留。

若进程在 `submitting` 状态崩溃，重启恢复时同样将遗留状态识别为提交结果不确定，不自动重放请求。

## 11. Provider 状态映射

Provider 适配器将 ModelScope 原始响应转换为封闭结果，不让原始字符串进入应用控制流。

概念结果：

```text
ProviderPending
ProviderRunning
ProviderSucceeded(list[ProviderImageReference])
ProviderFailed(ProviderFailure)
ProviderUnknownStatus
```

映射规则：

- ModelScope 等待/排队状态 → 保持 `submitted` 或转为 `in_progress`，具体映射由真实 API fixture 决定。
- ModelScope 运行/处理状态 → `in_progress`。
- ModelScope 成功且至少一个结果引用 → `succeeded` 并创建有序图片列表。
- ModelScope 明确失败 → `failed`。
- 成功但零图片 → `failed + EMPTY_OUTPUT_IMAGES`。
- 未知状态 → Job 状态保持不变，当前 check 返回 `UPSTREAM_STATUS_UNKNOWN`。

未知状态是可观察的上游契约错误，不假装成处理中，也不永久终止 Job。

## 12. ProviderImageReference

`ProviderImageReference` 是获取单张远程结果所需的敏感引用。

字段概念：

```text
locator: str
provider_metadata: minimal typed metadata
```

约束：

- locator 可以是 URL 或未来 API 返回的其他不透明标识。
- 领域和应用层不解析 locator。
- locator 视为敏感信息，不默认进入日志、列表摘要或 MCP 文本。
- 为支持重启后 fetch，必须以受控方式持久化。
- 上游重新查询返回更新引用时，允许在保持 `ImageId` 和 position 不变的前提下替换 locator。
- 不保存无使用价值的完整 Provider 响应。

## 13. GeneratedImage

每个上游结果创建一个 `GeneratedImage`。

字段：

```text
image_id: ImageId
position: int
provider_reference: ProviderImageReference
artifact_status: ArtifactStatus
artifact: LocalArtifact | None
last_error: DomainError | None
```

规则：

- `position` 从零开始，必须唯一且连续。
- 图片按 position 排序。
- 初始 artifact status 为 `pending`。
- `available` 必须包含 `LocalArtifact`，且当前错误为空。
- `pending` 和 `failed` 不得包含已经承诺有效的 LocalArtifact。
- 同一个 ImageId 在 locator 更新和重复 fetch 中保持不变。
- Job 成功后不能通过删除全部图片退回无结果状态。

## 14. ArtifactStatus

每张图片的持久化产物状态：

```text
pending
available
failed
```

含义：

- `pending`：已有上游引用，尚未成功生成本地产物。
- `available`：下载、验证、校验和原子保存全部成功。
- `failed`：最近一次下载、验证或保存失败，可以再次 fetch。

`downloading` 不持久化。它是一次 fetch 调用内部的瞬时过程，避免进程崩溃留下无法判断的僵尸状态。

允许转换：

```text
pending   → available | failed
failed    → available | failed
available → available
```

禁止自动重新下载 `available` 图片。未来如需强制重取，必须增加显式产品能力。

## 15. LocalArtifact

`LocalArtifact` 表达经过验证并成功提交的本地产物。

字段：

```text
artifact_key: ArtifactKey
relative_path: str
sha256: str
byte_size: int
media_type: str
format: str
width: int
height: int
saved_at: datetime
```

约束：

- `artifact_key` 是 Artifact Store 内的稳定逻辑键。
- `relative_path` 相对于配置的 artifact root。
- 领域对象不保存绝对路径。
- `sha256` 使用小写十六进制表达原始保存字节摘要。
- `byte_size`、宽和高必须为正数。
- `media_type` 与 `format` 来自实际内容验证，不盲信 HTTP Header 或文件扩展名。
- `LocalArtifact` 只有原子保存成功后才创建。

绝对路径或 MCP Resource URI 由应用/MCP 层基于 artifact root 和 LocalArtifact 派生。

## 16. 多图部分成功

Job `succeeded` 后，各图片产物可以独立成功或失败。

示例：

```text
image 0 → available
image 1 → failed
image 2 → available
```

规则：

- Job 保持 `succeeded`。
- 已成功图片不回滚。
- 重复 fetch 只处理 `pending` 和 `failed` 图片。
- 单张失败不阻止其他图片下载和保存。
- 工具返回成功产物与失败摘要。
- 所有失败图片允许后续重试。

聚合产物状态由图片集合派生：

```text
not_ready  Job 尚未 succeeded
pending    Job succeeded，尚无 available，且至少一张 pending
partial    至少一张 available，但不是全部 available
available  所有图片 available
failed     Job succeeded，没有 available，且所有图片 failed
```

聚合状态不单独持久化，避免与图片事实漂移。

## 17. DomainError

稳定领域错误字段：

```text
code: ErrorCode
stage: ErrorStage
category: ErrorCategory
retryable: bool
retry_after_seconds: int | None
safe_message: str
provider_request_id: str | None
possibly_submitted: bool
occurred_at: datetime
```

### 17.1 ErrorStage

```text
validation
configuration
submission
status_check
download
image_validation
artifact_save
persistence
state
internal
```

### 17.2 ErrorCategory

```text
input
configuration
network
upstream_http
upstream_task
upstream_contract
timeout
local_io
state_conflict
internal
```

### 17.3 约束

- `code` 是稳定的大写机器 reason code。
- `safe_message` 必须可以安全返回给 Agent。
- 原始异常、堆栈和完整上游正文不进入 DomainError。
- `retry_after_seconds` 非负。
- `possibly_submitted` 只在提交阶段有意义，其他阶段为 false。
- MCP suggestion 和工具 `next_action` 不属于 DomainError。
- Provider 内部错误先净化再进入领域/应用结果。

## 18. 当前错误生命周期

V1 保存聚合或图片的最近未解决错误，不建设完整事件审计系统。

规则：

- 操作失败时更新相应对象的 `last_error`。
- 随后的同阶段操作成功时清除对应 `last_error`。
- Job 上游失败进入终态后保留其最后错误。
- 图片成功转为 `available` 时清除图片错误。
- 图片错误不复制为 Job 终态错误。
- Repository 或 MCP 调用本身失败但未成功持久化时，不能假装错误已经成为领域事实。

完整操作日志由标准 logging 负责，不通过领域对象模拟审计系统。

## 19. Check 操作语义

一次 check：

- 对 `submitted` 或 `in_progress` Job 查询上游一次。
- 对 `succeeded` 或 `failed` Job 不访问上游，直接返回当前事实。
- 对 `submitting` Job 不自动提交或查询；遗留 `submitting` 进入不确定提交恢复流程。
- 网络、HTTP、解析或未知状态失败时，除明确上游终态外保持 Job 状态不变。
- 成功观察有效状态时清除可恢复的状态查询错误。

异步 check 不保存跨调用 poll attempt、最大轮询次数或退避指数。

## 20. Fetch 操作语义

一次 fetch：

- 只接受 `succeeded` Job。
- 对每张 `pending/failed` 图片独立尝试获取本地产物。
- 跳过 `available` 图片。
- 可以并发处理多张图片，但每张图片的结果独立提交。
- 不因为一个图片失败而取消已经完成的其他图片。
- 上游引用失效时可以通过 Provider 重新查询同一 Task 并刷新 locator，但不能创建新 Job 或新上游任务。
- 重复调用保持 ImageId、position 和已有 artifact 不变。

如果调用在下载中被取消：

- 未原子提交的临时文件被清理。
- 未完成图片保持原来的 `pending/failed` 状态。
- 已完成图片保持 `available`。
- Job 保持 `succeeded`。

## 21. Generate 阻塞编排语义

`generate_image` 是应用用例组合，不是领域对象或独立状态机。

它执行：

```text
submit
→ 等待
→ check
→ 重复直到成功、明确失败、取消或 max_wait_seconds 到期
→ succeeded 时 fetch
```

规则：

- 使用与独立工具相同的 Job 聚合和 Repository。
- `max_wait_seconds` 只限制本地等待。
- 本地超时返回 Job 当前事实和 Job ID。
- 本地超时不创建 Domain Job timeout 状态。
- 调用取消不伪造上游取消。

## 22. 下一步动作

`next_action` 不是领域字段，由应用层根据领域事实派生。

基本映射：

```text
submitted / in_progress
    → check_image_generation

succeeded + artifact aggregate != available
    → fetch_image_generation_result

succeeded + artifact aggregate == available
    → none

failed
    → none；根据 DomainError 提供人工/Agent 建议

submitting
    → 当前 submit 调用内等待；重启遗留时报告提交结果不确定
```

领域层不得导入或保存 MCP 工具名称。

## 23. 列表摘要

`list_image_generations` 使用应用层摘要投影，不直接暴露完整 GenerationJob。

摘要从领域事实派生：

- Job ID。
- Job 状态。
- 聚合产物状态。
- 图片总数与 available 数量。
- 创建/更新时间。
- 安全错误摘要。
- 下一步动作。

默认不包含：

- 完整 GenerationRequest。
- prompt 或 negative prompt。
- Provider locator。
- LocalArtifact 绝对路径。
- 原始 Provider 状态正文。

## 24. 旧行为映射

| 旧实现 | 新领域表达 | 处理 |
|---|---|---|
| 时间戳字符串 `job_id` | UUIDv7 `JobId` | 替换 |
| 单数 `remote_image_url` | 有序 `list[GeneratedImage]` 中的 ProviderImageReference | 替换 |
| 单数 `output_path` | 每张图片独立 LocalArtifact | 替换 |
| `result_ready` 布尔值 | `job.status == succeeded` | 派生，不持久化 |
| `local_file_ready` 布尔值 | 所有图片 `artifact_status == available` | 派生，不持久化 |
| `provider_status` 控制 Agent 流程 | ProviderTaskReference 诊断字段 | 降级为诊断 |
| Job `timeout` 终态 | 当前操作 DomainError，Job 状态不变 | 删除旧语义 |
| Job 中的 poll attempt | 不进入领域模型 | 删除 |
| Job 中的 backoff/max attempts | 应用等待策略或服务器配置 | 删除 |
| 成功只读取 `output_images[0]` | 保留完整有序结果列表 | 修复 |
| 保存失败只返回一次性工具错误 | 图片 `failed`，允许重复 fetch | 重建 |
| 图片失败改变整体调用结论 | Job 成功与图片产物独立 | 重建 |
| JSON 文件直接充当 Job schema | Repository 映射领域聚合 | 替换 |
| 任意绝对 output path | ArtifactKey + 安全相对路径 | 替换 |
| 重复工作流各自维护状态 | 统一聚合与应用用例 | 替换 |

## 25. 不兼容决策

新系统不兼容旧 JSON Job 文件，也不迁移旧运行时任务记录。

理由：

- 旧记录只支持单图片。
- 旧 `timeout` 语义与新状态机冲突。
- 旧路径和敏感字段缺少新的安全边界。
- 为兼容旧记录会污染新聚合和 SQLite schema。

`legacy/` 中的 fixture 用于验证旧行为理解，不作为新数据库迁移输入。

## 26. MCP 输入行为变更

新异步工具不再暴露：

```text
max_poll_attempts
poll_backoff
max_poll_interval_seconds
```

原因：

- 每次 `check_image_generation` 只查询一次。
- 跨调用轮询次数不是 Job 事实。
- 建议等待和退避属于服务编排策略。

阻塞 `generate_image` 只暴露明确的本地等待预算：

```text
max_wait_seconds
```

是否允许覆盖基础轮询间隔由 `05-mcp-interface-contract.md` 决定；它即使允许，也属于单次阻塞调用策略，不进入 GenerationRequest 或 GenerationJob。

## 27. 领域验收场景

至少覆盖：

1. submitting Job 在获得 Task ID 后转 submitted。
2. submitting 调用明确失败后转 failed。
3. 遗留 submitting Job 恢复为提交结果不确定失败。
4. submitted 经排队/运行转 in_progress。
5. submitted 或 in_progress 成功产生一张图片。
6. 成功产生多张有序图片和稳定 ImageId。
7. 成功响应没有图片时转 failed。
8. 未知 Provider 状态保持原 Job 状态。
9. check 网络超时保持原 Job 状态。
10. succeeded Job 的图片下载失败时仍保持 succeeded。
11. 多图片部分成功并正确派生 partial。
12. 重试 fetch 只处理 pending/failed 图片。
13. available 图片不会被重复下载或覆盖。
14. fetch 取消后保留已经原子提交的图片。
15. 非法 Job 和 Artifact 状态转换被拒绝。
16. LocalArtifact 不包含绝对路径。
17. DomainError 不包含原始异常、Token 或签名 URL。
18. next action 由应用层正确派生，不污染领域模型。

## 28. 后续文档约束

- `04-config-and-storage-schema.md` 必须将 GenerationJob 与 GeneratedImage 映射为规范化 SQLite 表，并通过 schema version 明确迁移。
- `04` 不得持久化可由图片集合稳定派生的聚合状态布尔值。
- `05-mcp-interface-contract.md` 必须使用本文的 JobStatus、ArtifactStatus 和 DomainError，不建立第二套同义枚举。
- `05` 的列表结果必须使用摘要投影，不直接序列化完整 GenerationJob。
- `06-core-organization.md` 必须让领域模块不依赖 Pydantic、MCP、HTTPX、aiosqlite、platformdirs 或 Pillow。
