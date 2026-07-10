# ModelScope Image Gen MCP v2 接口契约

## 文档状态

- 状态：已确认
- 前置文档：`00-rebuild-direction.md` 至 `04-config-and-storage-schema.md`
- 适用目标：重构后的 V1
- MCP SDK 目标：v2.0

本文定义 V1 的 MCP capability、五个工具、输入输出模型、结构化错误、`is_error`、分页、ToolAnnotations 和模型文本契约。应用用例不得依赖本文中的 MCP 类型；MCP 适配层负责在应用结果与协议结果之间转换。

## 1. MCP capability

V1 只声明：

```text
tools
```

不声明：

- resources。
- prompts。
- completions。
- experimental tasks。

工具集合在进程生命周期内固定，因此 `tools.list_changed=false`。

V1 使用 MCP v2 低层 `Server`，原因是需要同时精确控制：

- Tools-only capability。
- input/output schema。
- `content` 与 `structured_content`。
- `is_error`。
- ToolAnnotations。
- 协议错误与工具错误的边界。

## 2. ToolContract 适配层

低层 Server 不允许退化为手写 schema 和工具名条件分支。每个工具通过强类型 `ToolContract` 注册。

概念结构：

```text
ToolContract[InputModel, OutputModel]
├── name
├── title
├── description
├── input_model
├── output_model
├── annotations
├── application_handler
└── text_presenter
```

统一职责：

1. 使用 Pydantic input model 生成 `input_schema`。
2. 使用 Pydantic output model 生成 `output_schema`。
3. 设置 `additionalProperties=false`。
4. 验证客户端参数。
5. 调用对应应用 handler。
6. 将应用结果映射为具体 ToolOutput model。
7. 再次验证 structured content。
8. 通过 text presenter 生成简洁 TextContent。
9. 根据 `ok` 设置 `is_error`。
10. 将未预期异常净化为稳定 INTERNAL_ERROR。

工具通过名称到 ToolContract 的只读映射分发，不使用长 `if/elif` 链。

## 3. Schema 规则

- 输入和输出模型使用 Pydantic v2。
- 所有 input model 配置 `extra="forbid"`。
- 所有 output model 配置严格字段和稳定枚举。
- JSON Schema 由模型生成，不手写重复 schema。
- Tool definition 使用模型生成的 schema，并明确 `type=object`。
- 发送前使用 output model 验证 structured content。
- 测试通过 MCP Client 再次验证实际 wire result。
- 应用字段使用 snake_case；MCP SDK 自己负责协议 wrapper 的 wire alias。
- schema title 和 description 稳定，但客户端不能依赖自动生成的 Pydantic title 作为字段身份。

## 4. 公共 ToolEnvelope

五个工具的 concrete output 都遵循：

```text
ToolEnvelope[T]
├── ok: bool
├── data: T | null
└── error: ErrorOutput | null
```

每个工具发布具体 output schema，例如 `SubmitToolOutput`、`CheckToolOutput`，不在 wire schema 中暴露 Python 泛型。

不变量：

```text
ok=true
    data  != null
    error == null

ok=false
    error != null
    data  可以为空，也可以包含安全恢复上下文
```

失败时允许 data 存在，用于返回：

- 已创建的 Job ID。
- 状态未改变的当前 Job。
- 提交结果不确定的 failed Job。
- fetch 已经成功的部分图片。

## 5. ErrorOutput

```text
code: str
stage: ErrorStage
category: ErrorCategory
retryable: bool
retry_after_seconds: int | null
message: str
possibly_submitted: bool
provider_request_id: str | null
next_action: NextActionOutput | null
```

约束：

- code 是稳定大写 reason code。
- message 来自领域 `safe_message` 或经过净化的应用错误。
- retry_after_seconds 非负。
- Provider locator、Token、原始异常和上游正文不得出现。
- `provider_request_id` 仅在安全且有诊断价值时返回。
- suggestion 不作为自由文本字段；可执行建议优先表达为 next action。

## 6. 核心 reason code

V1 至少定义：

```text
ARGUMENT_VALIDATION_FAILED
INVALID_CURSOR
JOB_NOT_FOUND
INVALID_JOB_STATE
INVALID_JOB_TRANSITION
MODELSCOPE_TOKEN_MISSING
SUBMISSION_REJECTED
SUBMISSION_OUTCOME_UNKNOWN
NETWORK_ERROR
UPSTREAM_HTTP_ERROR
UPSTREAM_TASK_FAILED
UPSTREAM_STATUS_UNKNOWN
UPSTREAM_RESPONSE_INVALID
EMPTY_OUTPUT_IMAGES
RESULT_NOT_READY
DOWNLOAD_FAILED
DOWNLOAD_TOO_LARGE
IMAGE_VALIDATION_FAILED
IMAGE_TOO_LARGE
ARTIFACT_SAVE_FAILED
PERSISTENCE_ERROR
CONCURRENT_MODIFICATION
INTERNAL_ERROR
```

Provider 可以在适配层产生更细的内部错误，但只有经过接口文档登记的稳定 code 才能进入 MCP structured content。

## 7. 工具错误与协议错误

### 7.1 Tool result error

已知工具的输入或执行失败返回：

```text
CallToolResult
    is_error = true
    content = 简洁安全错误摘要
    structured_content = ToolEnvelope(ok=false, ...)
```

包括：

- Pydantic 参数校验失败。
- Job 不存在。
- 当前状态不允许操作。
- Token 缺失。
- 网络、上游、下载、验证、保存或持久化失败。
- 未预期内部异常净化后的 INTERNAL_ERROR。

### 7.2 Protocol error

只在请求本身不是合法工具调用时返回 MCP/JSON-RPC protocol error：

- 未知工具名。
- MCP 请求结构无效。
- 协议版本或服务器 capability 不满足请求。
- 低层 Server 无法形成合法 MCP response 的基础设施级故障。

已知工具的业务失败不能通过 `MCPError` 绕过 ToolEnvelope。

## 8. is_error 与 ok

正常对应：

```text
ok=true  → is_error=false
ok=false → is_error=true
```

以下语义特别锁定：

- `check_image_generation` 成功读取一个 `status=failed` 的 Job：`ok=true`、`is_error=false`。工具操作成功，Job 事实是失败。
- fetch 至少一张图片成功：`ok=true`，通过 `partial` 表达部分成功。
- fetch 没有任何图片成功且本次存在操作失败：`ok=false`、`is_error=true`。
- `generate_image` 本地等待预算耗尽并成功交回 Job：`ok=true`、`completed=false`、`is_error=false`。

## 9. NextActionOutput

```text
tool: NextToolName
job_id: str
recommended_wait_seconds: int | null
```

`NextToolName` 只允许：

```text
check_image_generation
fetch_image_generation_result
```

不使用任意 `arguments: dict`，因为 V1 下一步动作只有 Job ID，强类型字段更稳定。

规则：

- check 下一步可以包含建议等待时间。
- fetch 下一步不需要等待时间时为 null。
- 终态完成没有必需 next action。
- next action 由应用层派生，领域对象不保存 MCP 工具名。

## 10. JobOutput

```text
job_id: str
status: JobStatus
artifact_status: ArtifactAggregateStatus
is_terminal: bool
result_ready: bool
model: str
size: ImageSizeOutput
seed: int | null
image_count: int
available_image_count: int
created_at: str
updated_at: str
submitted_at: str | null
completed_at: str | null
last_error: ErrorOutput | null
next_action: NextActionOutput | null
```

派生字段：

- is_terminal 来自 JobStatus。
- result_ready 等价于 Job succeeded。
- artifact_status 来自 Job 和图片集合。
- image count 来自图片集合。
- next action 来自应用层。

JobOutput 不包含：

- prompt。
- negative prompt。
- Provider locator。
- SQLite revision。
- 原始 Provider 状态正文。
- 数据库位置。

## 11. ImageSizeInput 与 ImageSizeOutput

输入不再使用 `"1024x1024"` 字符串。

```text
ImageSizeInput
├── width: int = 1024
└── height: int = 1024
```

约束：

- 宽高为正整数。
- ModelScope 模型特定范围由 Provider 在提交前校验。
- 错误指向 `size.width` 或 `size.height`，不要求 Agent 学习自定义字符串格式。

输出使用相同结构但独立 DTO，避免输入默认值或验证配置污染输出模型。

## 12. GeneratedImageOutput

```text
image_id: str
position: int
artifact_status: ArtifactStatus
file_path: str | null
relative_path: str | null
sha256: str | null
byte_size: int | null
media_type: str | null
format: str | null
width: int | null
height: int | null
saved_at: str | null
last_error: ErrorOutput | null
```

规则：

- file path 和 LocalArtifact 字段只在 available 时存在。
- file_path 是当前机器上解析后的绝对路径。
- relative_path 相对于 artifact root。
- pending/failed 图片不返回 Provider locator。
- position 从零开始。
- 图片按 position 排序。

V1 不返回 base64 `ImageContent`：

- 多图和大图可能显著放大 stdio 负载。
- 原始文件已在本地安全落盘。
- Host 和后续工具可使用 file path。
- 未来如增加 Resources 或缩略图预览，作为独立产品能力设计。

## 13. submit_image_generation

### 13.1 Input

```text
SubmitImageGenerationInput
├── prompt: str
├── model: str | null = null
├── size: ImageSizeInput = {width: 1024, height: 1024}
├── negative_prompt: str | null = null
└── seed: int | null = null
```

规范化：

- prompt 去除首尾空白后必须非空。
- model null 使用服务器默认；非空字符串去除首尾空白。
- negative prompt 空字符串规范化为 null。
- seed 保持整数，上游范围由 Provider 校验。

明确不接受：

- output directory。
- output filename。
- Token。
- timeout。
- poll interval。
- max attempts。
- backoff。

### 13.2 Output data

```text
SubmitData
├── job: JobOutput
└── accepted: bool
```

成功：

- accepted=true。
- Job 通常为 submitted。

失败：

- 参数或配置失败：data 可以为空。
- 上游明确拒绝：data 包含 failed Job，accepted=false。
- 提交结果不确定：data 包含 failed Job，accepted=false，error.possibly_submitted=true。

## 14. check_image_generation

### 14.1 Input

```text
CheckImageGenerationInput
└── job_id: UUIDv7 string
```

### 14.2 Output data

```text
CheckData
└── job: JobOutput
```

行为：

- submitted/in_progress 查询上游一次。
- succeeded/failed 直接返回本地事实。
- 遗留 submitting 返回提交结果不确定错误。
- 网络/未知状态错误时 data 包含状态未改变的 Job。
- Job status=failed 的正常读取返回 ok=true。

## 15. fetch_image_generation_result

### 15.1 Input

```text
FetchImageGenerationResultInput
└── job_id: UUIDv7 string
```

### 15.2 Output data

```text
FetchData
├── job: JobOutput
├── images: list[GeneratedImageOutput]
└── partial: bool
```

行为：

- 只接受 succeeded Job。
- 跳过 available 图片。
- 对 pending/failed 图片执行受限并发 fetch。
- 全部 available：ok=true、partial=false。
- 至少一张 available、并有未成功图片：ok=true、partial=true。
- 没有任何图片 available 且本次失败：ok=false，data 仍包含 Job 和图片错误。
- 重复调用已完成 Job 不访问网络。

## 16. list_image_generations

### 16.1 Input

```text
ListImageGenerationsInput
├── statuses: list[JobStatus] | null = null
├── limit: int = 20
└── cursor: str | null = null
```

约束：

- limit 范围 `1..100`。
- statuses 去重并使用稳定顺序规范化。
- 空 statuses 列表规范化为 null 或拒绝，实现在 schema 中选择一种并保持测试固定；V1 推荐规范化为 null。
- cursor 是不透明字符串。

### 16.2 Pagination

使用 keyset pagination：

```text
ORDER BY updated_at DESC, job_id DESC
```

cursor 是版本化 base64url payload，至少绑定：

- cursor version。
- 上一项 updated_at。
- 上一项 job_id。
- statuses filter fingerprint。

规则：

- 不使用 offset。
- 不返回 total count。
- 非法、版本不支持或过滤条件不匹配返回 INVALID_CURSOR。
- 客户端不得构造或解析 cursor。

### 16.3 Summary

```text
JobSummaryOutput
├── job_id
├── status
├── artifact_status
├── model
├── size
├── image_count
├── available_image_count
├── created_at
├── updated_at
├── last_error_summary
└── next_action
```

不包含：

- prompt/negative prompt。
- Provider locator。
- 图片绝对或相对路径。
- 每张图片详情。
- 完整错误正文。

### 16.4 Output data

```text
ListData
├── items: list[JobSummaryOutput]
└── next_cursor: str | null
```

## 17. generate_image

### 17.1 Input

```text
GenerateImageInput
├── prompt
├── model
├── size
├── negative_prompt
├── seed
└── max_wait_seconds: float | null = null
```

`max_wait_seconds`：

- null 使用服务器默认值。
- 有效范围 `1..3600`。
- 只限制本地等待。
- 不改变 Job 状态机。

不暴露 poll interval。阻塞轮询节奏由服务器配置统一控制。

### 17.2 Output data

```text
GenerateData
├── job: JobOutput
├── images: list[GeneratedImageOutput]
├── completed: bool
└── partial: bool
```

行为：

- 完成：返回与 fetch 相同图片结构。
- 上游明确失败：ok=false，data 包含 failed Job。
- 本地等待超时：ok=true、completed=false、images 可为空、next action 为 check。
- 工具取消：保留 Job；调用按 MCP 取消语义结束，不伪造 canceled 状态。

## 18. ToolAnnotations

| 工具 | read_only_hint | destructive_hint | idempotent_hint | open_world_hint |
|---|---:|---:|---:|---:|
| `submit_image_generation` | false | false | false | true |
| `check_image_generation` | false | false | true | true |
| `fetch_image_generation_result` | false | false | true | true |
| `list_image_generations` | true | false | true | false |
| `generate_image` | false | false | false | true |

解释：

- submit/generate 创建外部任务并可能消耗额度，因此非幂等、open world。
- 创建任务不是 destructive update，但工具描述必须明确额度副作用。
- check 会访问网络并更新本地状态，因此不是 read-only；重复检查逻辑幂等。
- fetch 会写文件但不会覆盖 available 图片，重复调用逻辑幂等。
- list 只访问本地持久化摘要。

annotations 是 Host 提示，不是访问控制或安全边界。

## 19. Tool title 与 description

每个 Tool definition 提供稳定 title 和面向 Agent 的 description。

描述必须包含：

- 工具完成什么任务。
- 重要副作用。
- 何时使用。
- 何时不要使用。
- 通常下一步是什么。

默认工作流在 submit/check/fetch 描述中形成闭环。`generate_image` 明确标注为阻塞便利工具，并引导可调度 Agent 使用异步路径。

## 20. 模型文本 content

TextContent 是给模型阅读的简洁摘要，不重复 structured content 的完整 JSON。

示例：

```text
Image generation job submitted.
Job: 019...
State: submitted
Check again in about 5 seconds with check_image_generation.
```

```text
Image generation completed with 2 of 3 artifacts available.
Retry fetch_image_generation_result for the remaining image.
```

```text
Image generation status check failed temporarily.
Job 019... remains in_progress. Retry in about 5 seconds.
```

文本要求：

- 不嵌入 JSON 镜像。
- 不暴露 Provider locator、Token 或原始异常。
- 不依赖文本传递 structured content 中不存在的关键控制信息。
- 不输出完整 prompt。
- 多图片使用计数摘要，不枚举大段元数据。

## 21. ToolContract 验证顺序

```text
收到 tool call
→ 查找 ToolContract
→ Pydantic 验证 input
→ 调用 application handler
→ 映射 concrete output model
→ output model 验证
→ model_dump(mode="json", by_alias=true)
→ text presenter 生成 TextContent
→ ok 决定 is_error
→ 返回 CallToolResult
```

输入验证失败同样通过对应工具的 concrete ToolEnvelope 返回，不能让低层 Server 输出无结构的 Python ValidationError。

## 22. 意外异常

ToolContract 最外层捕获未预期异常：

- 记录净化后的内部日志和 correlation context。
- structured content 返回 INTERNAL_ERROR。
- message 使用稳定通用文本。
- retryable=false，除非错误分类器有明确证据。
- 不返回异常类名、repr 或 traceback。
- is_error=true。

`KeyboardInterrupt`、进程取消和系统退出类异常不转换为普通 tool error。

## 23. MCP 契约测试

每个工具至少测试：

- tools/list 中 name、title、description。
- input schema 与 output schema snapshot。
- ToolAnnotations。
- 合法输入 wire round-trip。
- extra field 被拒绝。
- 参数错误返回结构化 envelope 和 is_error=true。
- success 返回 is_error=false。
- structured content 通过 output model 验证。
- TextContent 简洁且不包含 JSON 镜像。
- 错误文本不泄露敏感字段。

跨工具测试：

- 只声明 Tools capability。
- 五个工具顺序固定，利于 Host 缓存和可预测展示。
- submit 的 next action 指向 check。
- check success 的 next action 指向 fetch。
- generate timeout 指向 check。
- list cursor 与 filter 绑定。
- fetch partial 和全失败具有不同 ok/is_error。
- Job failed 的成功 check 不被错误标记为 tool error。

## 24. 明确不兼容

V1 不兼容旧工具接口中的：

- `get_image_generation_status` 名称。
- `get_image_generation_result` 名称。
- `size="WIDTHxHEIGHT"` 字符串。
- `output_filename`。
- `output_dir`。
- `poll_interval_seconds`。
- `max_poll_attempts`。
- `poll_backoff`。
- `max_poll_interval_seconds`。
- 文本中镜像完整 JSON 的返回格式。

不提供隐藏 alias 或兼容工具，避免 Host 同时看到重复能力。

## 25. 后续文档约束

- `06-core-organization.md` 必须将 ToolContract、Pydantic MCP DTO 和 text presenter 限制在 MCP 适配层。
- `06` 的应用 handlers 返回应用结果，不返回 CallToolResult。
- `07-agent-experience.md` 必须使用本文的工具名称、副作用、文本层级和默认异步引导。
- `08-implementation-brief.md` 必须包含 tools/list schema、annotations、is_error、分页和敏感信息测试。
