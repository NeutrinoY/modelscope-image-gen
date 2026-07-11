# ModelScope Image Gen MCP Agent 体验与可观测性

## 文档状态

- 状态：已确认
- 前置文档：00-rebuild-direction.md 至 06-core-organization.md
- 适用目标：重构后的 V1

本文定义 V1 的 MCP Server 元数据、工具发现体验、模型文本呈现、错误语言、日志事件、用户文档和真实 Host 验收。本文只组织已经存在的应用事实，不增加新的业务状态、错误语义或工具能力。

Presenter 不得执行状态转换、访问 Provider、读取 Repository、判断重试策略或写入文件。所有 TextContent 都必须由经过验证的 structured content 和应用结果派生。

## 1. 体验目标

V1 的主要用户是 Agent，MCP Host 是程序化消费者，本地操作者负责配置和诊断。

Agent 体验必须让调用方在每次工具调用后回答：

1. 本次操作是否成功。
2. 当前 Job 处于什么状态。
3. 是否已经产生可用本地产物。
4. 下一步应该调用哪个工具。
5. 如果失败，是否值得重试以及何时重试。
6. 是否存在重复提交或重复计费风险。

体验层采用双通道 Agent-first 设计：

- structured content 是完整、严格、机器可验证的事实源。
- TextContent 是 Agent 可直接执行的简洁操作摘要。
- 两者表达相同事实，但 TextContent 不镜像 JSON。
- 工具描述在调用前说明用途、副作用、适用时机和下一步。
- 日志服务于本地诊断，不成为 Agent 控制流或领域事实来源。

## 2. 语言策略

MCP wire 层统一使用英文：

- Server name、title 和 instructions。
- 工具 name、title 和 description。
- 参数名、枚举值和错误 code。
- TextContent。
- 日志 event 名和字段名。

用户文档提供：

- README.md：完整英文文档。
- README.zh-CN.md：内容等价的完整中文文档。

两份 README 必须保持相同章节、配置项、工具能力和安全说明。中文文档不得成为省略关键边界的摘要版。

不本地化：

- 工具名称。
- JSON 字段。
- Error code。
- 环境变量。
- 日志 event。

这保证不同语言的 Host 配置、诊断搜索和自动化逻辑使用同一契约。

## 3. Server 身份

固定元数据：

~~~text
name: modelscope-image-gen-mcp
title: ModelScope Image Generation
version: importlib.metadata.version("modelscope-image-gen-mcp")
~~~

版本唯一事实来源是 pyproject.toml 的项目版本。Server、CLI 和发布元数据不得分别硬编码版本。

Server instructions 必须表达：

~~~text
Prefer submit_image_generation, then check_image_generation, then
fetch_image_generation_result for long-running image generation.
Use list_image_generations to recover previously created jobs.
Use generate_image only when the caller can wait synchronously.
~~~

允许在不改变语义的前提下调整换行，但必须保留：

- 异步路径是默认路径。
- list 用于恢复。
- generate 是阻塞便利能力。

## 4. Capability 与工具顺序

V1 只声明 Tools capability。不得为展示 MCP 能力而增加空壳 prompts、resources、completions 或 experimental tasks。

tools/list 始终按以下顺序返回：

1. submit_image_generation
2. check_image_generation
3. fetch_image_generation_result
4. list_image_generations
5. generate_image

该顺序由 ToolContract registry 定义并通过契约快照保护。它不是业务优先级枚举，但需要在不同 Host、平台和进程中保持稳定。

## 5. 工具 title 与 description

### 5.1 Submit Image Generation

名称：

~~~text
submit_image_generation
~~~

描述必须说明：

- 创建新的 ModelScope 异步文生图任务。
- 会访问外部服务并可能消耗配额。
- 返回本地 Job ID，不等待图片完成。
- 可调度 Agent 应从此工具开始。
- 通常下一步是 check_image_generation。
- 不能安全假定重复调用不会创建重复任务。

### 5.2 Check Image Generation

名称：

~~~text
check_image_generation
~~~

描述必须说明：

- 对 submitted/in_progress Job 最多执行一次上游状态查询。
- 会访问网络并更新本地状态。
- 不创建新任务，不下载图片。
- succeeded/failed Job 直接返回本地事实。
- 未完成时通常继续 check，成功时通常进入 fetch。

### 5.3 Fetch Image Generation Result

名称：

~~~text
fetch_image_generation_result
~~~

描述必须说明：

- 只处理已经 succeeded 的 Job。
- 下载、验证并安全保存尚未 available 的图片。
- 会访问网络并写入本地文件。
- available 图片不会重复下载或覆盖。
- 允许部分成功，失败图片可以后续重试 fetch。

### 5.4 List Image Generations

名称：

~~~text
list_image_generations
~~~

描述必须说明：

- 从本地 SQLite 读取任务摘要。
- 不访问 ModelScope，不刷新任务状态。
- 用于找回丢失的 Job ID 和恢复工作流。
- 不返回 prompt、Provider locator 或产物路径。
- 支持状态过滤和不透明 cursor 分页。

### 5.5 Generate Image

名称：

~~~text
generate_image
~~~

描述必须说明：

- 是 submit/check/fetch 的阻塞便利编排。
- 会访问外部服务、可能消耗配额、等待并写入文件。
- 不应成为可调度 Agent 的默认选择。
- 到达本地等待预算时返回 Job ID 和异步接续方式。
- 本地超时或取消不代表上游任务已取消。

## 6. ToolAnnotations 与描述一致性

ToolAnnotations 使用 05 文档锁定的值。描述、annotations 和真实实现必须一致：

| 工具 | read-only | idempotent | open-world | 关键说明 |
|---|---:|---:|---:|---|
| submit | false | false | true | 可能创建外部任务并消耗配额 |
| check | false | true | true | 一次上游查询并更新本地事实 |
| fetch | false | true | true | 网络访问与受控文件写入 |
| list | true | true | false | 只读本地摘要 |
| generate | false | false | true | 创建任务、等待并写入产物 |

Annotations 是 Host 提示，不是权限系统。不能为了减少审批提示而错误标记工具。

## 7. 双通道响应契约

每个已知工具调用同时返回：

- structured content：对应工具的 concrete ToolEnvelope。
- content：恰好一个 TextContent 操作摘要。
- is_error：严格由 ToolEnvelope.ok 映射。

structured content 负责：

- 完整 JobOutput 或 JobSummaryOutput。
- 完整 GeneratedImageOutput 列表。
- ErrorOutput。
- NextActionOutput。
- partial、completed、accepted 和 cursor 等机器字段。

TextContent 负责：

- 本次操作结果。
- Job ID 和当前状态。
- 下一工具与建议等待时间。
- retryable 和 possibly_submitted 风险。
- fetch/generate 返回的 available 本地路径。
- list 返回的紧凑恢复摘要。

TextContent 不能包含 structured content 中不存在的新事实。

## 8. TextContent 信息层级

固定优先级：

1. 本次操作结果。
2. Job ID 与当前状态。
3. 下一步动作。
4. 重试性、等待时间或重复提交风险。
5. 可用产物路径。
6. 必要的安全诊断标识。

文本使用短句和一行一个稳定字段。禁止：

- 完整 JSON 镜像。
- Markdown 表格。
- emoji。
- ANSI 颜色。
- 完整 prompt。
- Provider locator 或签名 URL。
- 原始上游响应。
- Python 异常类、repr 或 traceback。
- SQLite revision、数据库路径或内部对象表示。

## 9. 成功文本模板

Presenter 可以使用共享模板函数，但每个工具拥有独立语义模板。字段缺失时只省略对应行，不输出 null、None 或空占位。

### 9.1 Submit

~~~text
Image generation job submitted.
Job: <job_id>
State: submitted
Next: Call check_image_generation after about <seconds> seconds.
~~~

若上游在成功提交后返回不同的合法当前状态，State 使用实际领域状态。

### 9.2 Check：未完成

~~~text
Image generation is still in progress.
Job: <job_id>
State: <submitted|in_progress>
Next: Call check_image_generation after about <seconds> seconds.
~~~

### 9.3 Check：上游成功

~~~text
Image generation completed upstream.
Job: <job_id>
State: succeeded
Artifacts: <available>/<total> available
Next: Call fetch_image_generation_result.
~~~

如果所有产物已经 available，则省略 Next，并明确：

~~~text
Artifacts: <total>/<total> available
~~~

### 9.4 Check：Job 已失败

成功读取一个 failed Job 是成功的工具操作，使用 is_error=false：

~~~text
Image generation job is in a failed terminal state.
Job: <job_id>
State: failed
Reason: [<code>] <safe_message>
Retryable: <yes|no>
~~~

这与“本次 check 调用失败”严格区分。

### 9.5 Fetch

~~~text
Image generation artifacts fetched.
Job: <job_id>
State: succeeded
Artifacts: <available>/<total> available
Partial: <yes|no>
Files:
- <absolute_path_1>
- <absolute_path_2>
~~~

Files 枚举本次返回中所有 available 图片路径，按 position 排序。它不枚举 hash、字节数、Provider 信息或其他大段元数据。

部分成功时增加：

~~~text
Next: Call fetch_image_generation_result again for the remaining artifacts.
~~~

### 9.6 List

空列表：

~~~text
No image generation jobs matched the request.
~~~

非空列表：

~~~text
Image generation jobs: <count>
<job_id> | <status> | artifacts=<artifact_status> | updated=<timestamp> | next=<tool-or-none>
<job_id> | <status> | artifacts=<artifact_status> | updated=<timestamp> | next=<tool-or-none>
Next cursor: <opaque_cursor|none>
~~~

每个返回 item 使用一行。文本不出现 prompt、路径、Provider locator 或完整错误。存在下一页时，TextContent 原样提供 structured content 中的 cursor，确保只向模型展示文本的 Host 也能继续分页。Agent 只能逐字复制 cursor 到下一次 list 调用，不得解析、修改或自行构造。

### 9.7 Generate：完成

~~~text
Image generation completed.
Job: <job_id>
State: succeeded
Artifacts: <available>/<total> available
Partial: <yes|no>
Files:
- <absolute_path_1>
~~~

### 9.8 Generate：等待预算到期

等待预算到期是可恢复交接，不是 tool error：

~~~text
Image generation is still running after the local wait limit.
Job: <job_id>
State: <submitted|in_progress>
Completed: no
Next: Call check_image_generation after about <seconds> seconds.
~~~

不能使用 “task timed out” 或 “generation failed” 暗示上游终止。

## 10. 工具错误文本

已知工具失败使用：

~~~text
[<CODE>] <safe_message>
Retryable: <yes|no>
Job: <job_id>
Next: <safe actionable instruction>
Provider request: <request_id>
~~~

规则：

- 第一行始终是稳定 code 和安全 message。
- Retryable 始终存在。
- Job、Next 和 Provider request 只有有值时出现。
- 可执行下一步优先来自 NextActionOutput。
- 不从任意异常字符串推断重试建议。
- 不输出 error category、stage 等全部结构化字段，除非该信息对 Agent 决策必要。

### 10.1 提交结果不确定

SUBMISSION_OUTCOME_UNKNOWN 必须明确阻止自动重提：

~~~text
[SUBMISSION_OUTCOME_UNKNOWN] The request may have reached ModelScope, but no reliable task identifier was recorded.
Retryable: no
Job: <job_id>
Next: Do not submit the same request automatically. Review the failed job before deciding whether to create a new one.
~~~

possibly_submitted=true 时，Presenter 不得输出任何 “retry submit” 建议。

### 10.2 临时检查失败

~~~text
[NETWORK_ERROR] The image generation status could not be refreshed.
Retryable: yes
Job: <job_id>
Next: Call check_image_generation after about <seconds> seconds.
~~~

文本必须说明 Job 保持原状态，不把本次查询失败描述为 Job 失败。

### 10.3 Fetch 全失败

data 中仍可包含 Job 和图片恢复上下文：

~~~text
[DOWNLOAD_FAILED] No image artifact could be fetched in this attempt.
Retryable: yes
Job: <job_id>
Next: Call fetch_image_generation_result again after about <seconds> seconds.
~~~

## 11. 确定性格式

- 时间统一为 RFC 3339 UTC。
- 布尔文本统一为 yes/no。
- Job 状态和错误 code 使用 wire 枚举原值。
- 图片按 position 升序。
- 列表按 updated_at DESC、job_id DESC。
- 文件路径使用当前操作系统解析后的绝对路径。
- 字段顺序固定。
- 句尾标点固定。
- 文本不根据 Host、locale 或终端能力变化。

相同 structured content 必须产生相同 TextContent。时间和路径不得在 Presenter 内重新查询或重算。

## 12. 敏感信息边界

工具 description、TextContent、日志和文档示例不得泄露：

- ModelScope Token。
- Authorization Header。
- Cookie。
- Provider image locator 或签名 URL。
- 原始上游 response body。
- 完整 prompt 或 negative prompt。
- Python traceback。

允许返回：

- 安全 error message。
- 脱敏 Provider request ID。
- fetch/generate 中 available 产物的本地绝对路径。
- structured content 中已批准的相对产物路径和校验元数据。

list 不返回本地产物路径。默认日志也不记录产物绝对路径；使用 artifact_key、job_id 和 image_id 关联诊断。

## 13. 日志输出

使用 Python 标准库 logging。stdio 模式必须满足：

- stdout 只承载 MCP 协议。
- 日志只写 stderr，或未来显式配置的日志文件。
- 不使用 print 输出诊断。
- 每条记录单行。
- 默认 UTF-8 可安全显示。
- 不引入 structlog、loguru 或远程 telemetry SDK。

默认格式采用稳定 key=value 结构：

~~~text
timestamp=<utc> level=<level> event=<event> job_id=<id> stage=<stage> duration_ms=<integer>
~~~

字段值通过 logging 参数传递，不通过拼接未净化的第三方异常构建。

## 14. 日志事件

Server 与启动：

~~~text
server.starting
server.ready
server.stopping
server.stopped
server.startup_failed
~~~

数据库与恢复：

~~~text
database.opened
database.migrated
recovery.submitting_marked_uncertain
maintenance.temp_cleanup_completed
maintenance.retention_completed
maintenance.artifact_cleanup_completed
~~~

任务：

~~~text
job.submit.started
job.submit.succeeded
job.submit.failed
job.submit.uncertain
job.status.checked
job.status.changed
job.status.check_failed
~~~

产物：

~~~text
artifact.fetch.started
artifact.fetch.succeeded
artifact.fetch.failed
artifact.metadata_repaired
~~~

未预期错误：

~~~text
tool.internal_error
~~~

event 名属于可观测性契约。新增事件可以扩展，已发布事件不得在无迁移说明时改变含义。

## 15. 日志字段

按事件使用最小必要字段：

~~~text
event
job_id
image_id
stage
from_status
to_status
provider_request_id
artifact_key
duration_ms
retryable
possibly_submitted
error_code
~~~

禁止字段：

- prompt、negative_prompt。
- token、authorization、cookie。
- Provider locator 或完整 URL。
- 原始请求/响应 body。
- 图片字节。
- 用户主目录绝对路径。
- exception repr。

DEBUG 可以记录经过净化的 payload 字段集合、HTTP status、响应 schema 分支和内容长度，但不能降低敏感信息标准。

## 16. 日志等级

- INFO：Server 生命周期、正常 Job 状态转换、产物成功、迁移完成。
- WARNING：可重试上游失败、未知上游状态、单项清理失败、提交结果不确定。
- ERROR：启动失败、数据库不可用、迁移失败、未预期内部异常。
- DEBUG：净化后的协议形状、映射分支和性能诊断。

预期的输入错误、Job not found 或 invalid state 不默认输出 ERROR traceback。ToolContract 已向调用方返回结构化结果时，日志级别依据运维价值而不是 is_error 机械决定。

## 17. 启动与关闭可见性

server.ready 只能在以下步骤全部完成后记录：

- 配置解析。
- 目录准备。
- SQLite 打开和迁移。
- submitting 恢复。
- 必要维护。
- HTTP Client、Repository、Artifact Store、用例和 ToolContract 完成组装。

server.startup_failed 记录安全阶段和稳定错误分类，CLI 向 stderr 输出简洁原因并返回非零退出码。

关闭时先记录 server.stopping，资源按创建逆序释放，全部释放后记录 server.stopped。取消和 KeyboardInterrupt 不记录为内部错误。

## 18. 用户文档

根目录至少包含：

~~~text
README.md
README.zh-CN.md
CHANGELOG.md
SECURITY.md
LICENSE
~~~

README 两种语言都包含：

1. 产品定位和 V1 边界。
2. Python 3.14、uv 和 uvx 快速开始。
3. Windows、macOS、Linux MCP Host 配置。
4. 默认 submit/check/fetch 工作流。
5. generate 阻塞便利工作流。
6. 五个工具和副作用。
7. 环境变量与默认目录。
8. 本地数据、隐私、retention 和备份说明。
9. 常见错误与恢复方式。
10. 开发、质量门禁、构建和 live 测试。
11. 发布与安全报告入口。

LICENSE 使用 MIT。SECURITY.md 说明支持版本、私密漏洞报告方式、敏感数据范围和 Token 泄漏应对。CHANGELOG 使用清晰版本章节记录破坏性工具/schema 变化。

README 示例中的版本号不得硬编码为运行时事实。示例 Token 只能使用明显占位符。

## 19. 必备工作流示例

文档和测试共同覆盖：

1. 异步单图成功。
2. 异步多图成功。
3. generate 等待预算到期后切换到 check/fetch。
4. 使用 list 找回 Job ID。
5. 多图部分产物失败后重复 fetch。
6. 缺少 Token 但服务可启动并使用 list。
7. 提交结果不确定且禁止自动重提。
8. 未知 Provider 状态但 Job 状态不被伪造。
9. available 产物重复 fetch 不重复下载。

示例必须使用新工具名、size 对象和受控产物路径，不保留旧接口兼容写法。

## 20. Agent 体验测试

MCP contract 测试至少验证：

- Server name、title、version 和 instructions。
- 只声明 Tools capability。
- 五工具顺序。
- title、description、input/output schema 和 annotations 快照。
- 每个成功、等待、失败、部分成功模板。
- structured content 与 TextContent 事实一致。
- TextContent 不包含 JSON 镜像。
- fetch/generate 枚举全部 available 路径。
- list 每项一行且不包含 prompt、locator 或路径。
- failed Job 的成功 check 使用 is_error=false。
- generate 等待预算到期使用 is_error=false。
- possibly_submitted 不建议自动重提。
- 同一 structured content 产生确定性文本。

敏感信息测试使用哨兵值注入：

- Token。
- prompt。
- Authorization Header。
- Provider locator。
- response body secret。

断言这些值不会出现在 TextContent、工具错误、日志或 schema description。

## 21. 真实 Host 验收

发布前执行：

- 官方 MCP 内存 Client 契约测试。
- MCP Inspector 人工检查。
- Windows 与 Ubuntu 的真实 stdio 子进程测试。
- 至少两个真实 MCP Host 调用验证，其中至少一个运行在 Windows。
- 从构建 wheel 安装后重复 stdio 冒烟测试。

真实 Host 验收至少完成：

1. tools/list 正确展示五个工具。
2. Host 能读取 structured content。
3. Agent 只依赖 TextContent 也能完成 submit/check/fetch。
4. Host 取消 generate 后服务仍可继续使用。
5. stdout 没有任何日志污染。
6. 本地路径在对应平台可被用户定位。

真实 ModelScope live 测试需要显式 Token 和环境标志，默认测试套件不得产生配额消耗。

## 22. 不采用

V1 不采用：

- structured-only 响应。
- prose-only 响应。
- JSON 镜像 TextContent。
- emoji 或终端颜色作为状态信号。
- Host/locale 特定文本分支。
- 在 description 中隐藏额度、网络或文件副作用。
- prompt、签名 URL 或绝对产物路径的默认日志。
- 远程 analytics、usage tracking 或崩溃上传。
- prompts/resources 作为工具文档替代品。
- MCP 工具形式的日志、删除或管理控制面。

## 23. 验收标准

07 完成时必须满足：

1. Agent 在每次工具返回后都能从 TextContent 确认状态和下一步。
2. Host 能从 structured content 得到完整强类型事实。
3. TextContent 和 structured content 不产生语义冲突。
4. submit/generate 明确披露外部配额副作用。
5. generate 明确是次要阻塞入口。
6. fetch/generate 返回全部 available 本地路径。
7. list 能帮助恢复 Job 且不泄露敏感大字段。
8. 提交结果不确定不会诱导自动重试。
9. stdio stdout 只包含 MCP 协议。
10. 日志事件稳定、可关联且无敏感信息。
11. 英文与中文 README 能独立指导完整安装、调用、恢复和诊断。
12. 内存 Client、Inspector、跨平台 stdio 和真实 Host 验收都有明确入口。

## 24. 后续文档约束

- 08-implementation-brief.md 必须把 TextContent、日志泄漏和真实 Host 验收列入完成门禁。
- 实现阶段 Presenter 只能消费 MCP DTO 或安全应用视图，不能导入 Infrastructure。
- 工具 description 与 ToolAnnotations 必须在同一 ToolContract 中注册，避免分散事实来源。
- 日志事件通过边界 helper 统一字段和净化规则，但不得建立无归属的 utils.py。
- 任何新增用户可见工具、状态或错误 code 都必须先修订 01、03 或 05，而不能只修改本文文案。
