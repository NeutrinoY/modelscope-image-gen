# ModelScope Image Gen MCP 配置与存储契约

## 文档状态

- 状态：已确认
- 前置文档：`00-rebuild-direction.md`、`01-product-and-information-architecture.md`、`02-technology-stack-decisions.md`、`03-domain-model-and-behavior-map.md`
- 适用目标：重构后的 V1

本文定义 V1 的进程配置、默认目录、SQLite schema、事务与并发、敏感数据、Artifact Store、清理和启动恢复契约。数据库和文件系统实现必须映射领域模型，不能建立第二套任务状态或产物事实。

## 1. 配置原则

- 服务器配置来自环境和明确默认值，不来自 MCP 工具参数。
- 配置在启动阶段解析和校验，并通过依赖注入传递。
- 缺失 ModelScope Token 不阻止服务启动，但阻止需要上游访问的操作。
- 安全上限不能被 Agent 参数突破。
- 默认目录不依赖当前工作目录。
- Token、路径和保留策略不进入 GenerationRequest。
- 配置对象不进入领域层。

## 2. 环境变量命名

项目配置统一使用：

```text
MODELSCOPE_IMAGE_GEN_
```

前缀。

ModelScope Token 保留其生态约定名称：

```text
MODELSCOPE_SDK_TOKEN
```

V1 不提供旧环境变量别名。重构后的 README、MCP Host 示例和诊断信息只记录本文中的正式名称。

## 3. 上游配置

| 环境变量 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `MODELSCOPE_SDK_TOKEN` | secret string | 空 | ModelScope Token；上游操作必需 |
| `MODELSCOPE_IMAGE_GEN_API_BASE` | URL/string | `https://api-inference.modelscope.cn/` | ModelScope API 基础地址 |
| `MODELSCOPE_IMAGE_GEN_DEFAULT_MODEL` | string | `krea/Krea-2-Turbo` | 默认文生图模型 |

约束：

- API base 规范化为恰好一个结尾 `/`。
- API base 只允许 `https`；测试环境可通过显式测试设置使用本地 HTTP transport，不把 HTTP 生产开关暴露为普通配置。
- 默认模型去除首尾空白后必须非空。
- Token 使用 `SecretStr` 或等价敏感类型，字符串表示不得暴露实际值。

### 3.1 Token 缺失行为

Token 缺失不阻止 MCP 服务启动。

仍可使用：

- `list_image_generations`。
- 读取已经持久化的终态任务。
- 返回已经 available 的本地产物信息。

需要上游访问时返回稳定配置错误：

```text
code      = MODELSCOPE_TOKEN_MISSING
stage     = configuration
category  = configuration
retryable = false
```

服务不热加载 Token。环境变化后需要重启进程。

## 4. 目录配置

| 环境变量 | 类型 | 默认值 |
|---|---|---|
| `MODELSCOPE_IMAGE_GEN_DATA_DIR` | path | platformdirs 用户数据目录 |
| `MODELSCOPE_IMAGE_GEN_DATABASE_PATH` | path | `<data_dir>/state.sqlite3` |
| `MODELSCOPE_IMAGE_GEN_ARTIFACT_ROOT` | path | `<data_dir>/artifacts` |

解析优先级：

```text
显式 DATABASE_PATH > DATA_DIR 派生数据库路径
显式 ARTIFACT_ROOT > DATA_DIR 派生产物目录
```

启动校验：

- 路径展开用户目录和环境支持的合法路径表示。
- 解析为规范化绝对路径。
- data directory 和 artifact root 不能指向普通文件。
- database path 不能指向目录。
- 必须能够创建或访问必要父目录。
- 路径不得位于项目的 `legacy/` 归档目录内。
- 默认路径不读取 MCP Host 当前工作目录。
- 数据库必须位于本地文件系统；网络共享目录不属于支持场景。

配置层负责解析路径，Repository 和 Artifact Store 接收已经验证的绝对根路径。

## 5. 网络与工作流配置

| 环境变量 | 类型 | 默认值 | 约束 |
|---|---:|---:|---|
| `MODELSCOPE_IMAGE_GEN_SUBMIT_TIMEOUT_SECONDS` | float | `30` | `> 0` |
| `MODELSCOPE_IMAGE_GEN_STATUS_TIMEOUT_SECONDS` | float | `30` | `> 0` |
| `MODELSCOPE_IMAGE_GEN_DOWNLOAD_TIMEOUT_SECONDS` | float | `60` | `> 0` |
| `MODELSCOPE_IMAGE_GEN_BLOCKING_POLL_INTERVAL_SECONDS` | float | `5` | `> 0` |
| `MODELSCOPE_IMAGE_GEN_DEFAULT_MAX_WAIT_SECONDS` | float | `600` | `> 0` |
| `MODELSCOPE_IMAGE_GEN_MAX_CONCURRENT_DOWNLOADS` | int | `4` | `>= 1` |
| `MODELSCOPE_IMAGE_GEN_MAX_DOWNLOAD_BYTES` | int | `52428800` | `> 0` |
| `MODELSCOPE_IMAGE_GEN_MAX_IMAGE_PIXELS` | int | `40000000` | `> 0` |

约束：

- 超时配置按提交、状态和下载阶段独立使用。
- `DEFAULT_MAX_WAIT_SECONDS` 是阻塞工具的默认本地等待预算，不是上游 Job timeout。
- 工具参数不能覆盖下载字节、图片像素和并发安全上限。
- 阻塞工具允许的 `max_wait_seconds` 范围由 MCP 接口文档定义。
- 配置值不持久化到 GenerationJob；Job 记录业务事实，不记录本次进程策略快照。

## 6. 日志与保留配置

| 环境变量 | 类型 | 默认值 | 说明 |
|---|---:|---:|---|
| `MODELSCOPE_IMAGE_GEN_LOG_LEVEL` | string | `INFO` | 标准 logging 等级 |
| `MODELSCOPE_IMAGE_GEN_TERMINAL_JOB_RETENTION_DAYS` | int | `0` | `0` 表示不自动删除正式 Job/图片 |
| `MODELSCOPE_IMAGE_GEN_TEMP_FILE_RETENTION_HOURS` | int | `24` | 临时文件最长保留时间 |

约束：

- retention 值必须非负。
- 正式 Job 和产物默认不自动删除。
- 临时文件清理默认启用。
- 自动清理只处理本系统拥有且位于受控目录中的路径。
- 单个清理错误记录警告，不阻止服务正常启动。

## 7. 敏感数据策略

V1 为完整恢复 GenerationJob，持久化：

- prompt。
- negative prompt。
- Provider image locator。
- Provider request ID。
- 安全错误信息。

敏感边界：

- Token 永远不进入 SQLite。
- Authorization Header 永远不进入 SQLite。
- prompt 和 negative prompt 不进入列表摘要或默认日志。
- Provider locator 不进入列表摘要、普通 MCP 文本或默认日志。
- 原始 Provider 响应和完整错误正文不持久化。
- SQLite 主文件、WAL、SHM 和备份都视为敏感数据。

V1 不提供 `STORE_PROMPTS=false` 模式。可选不持久化 prompt 会产生无法完整重建的残缺 Job，并迫使领域层支持第二种聚合形态。

V1 不实现应用层 SQLite 加密。保护手段是：

- platformdirs 用户私有目录。
- POSIX 上创建目录时使用用户私有权限，文件使用用户读写权限。
- Windows 上使用当前用户目录继承的访问控制。
- 操作者可配置 retention。
- 文档明确提示数据库包含敏感业务数据。

## 8. SQLite 连接与运行设置

Repository 打开连接后执行：

```sql
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA busy_timeout = 5000;
```

规则：

- Connection 在应用 lifespan 中创建和关闭。
- 所有写操作使用显式事务。
- 不在数据库事务中执行 HTTP 请求、图片下载或 Pillow 验证。
- Repository 捕获并转换 SQLite 异常，不把 SQL 或 aiosqlite 类型泄露到应用层。
- 数据库位于本地文件系统。
- V1 正式支持一个 data directory 对应一个 MCP 服务进程。

## 9. Schema 版本与迁移

使用：

```sql
PRAGMA user_version;
```

记录 schema 版本。

V1 初始 schema version 为 `1`。

迁移规则：

- 迁移函数按 `N → N+1` 显式实现。
- 每次迁移在独立事务中执行。
- 成功完成后更新 `user_version`。
- 数据库版本高于当前程序支持版本时拒绝写入并拒绝正常启动。
- 迁移失败时回滚并拒绝启动。
- 不通过检查列名猜测旧 schema。
- 不导入 legacy JSON Job 文件。
- 迁移测试必须从每个受支持旧 schema fixture 升级到当前版本。

## 10. generation_jobs 表

逻辑 schema：

```text
job_id                     TEXT PRIMARY KEY
revision                   INTEGER NOT NULL
status                     TEXT NOT NULL

prompt                     TEXT NOT NULL
model                      TEXT NOT NULL
size_width                 INTEGER NOT NULL
size_height                INTEGER NOT NULL
negative_prompt            TEXT
seed                       INTEGER

provider                   TEXT
provider_task_id           TEXT
provider_request_id        TEXT
last_provider_status       TEXT

error_code                 TEXT
error_stage                TEXT
error_category             TEXT
error_retryable            INTEGER
error_retry_after_seconds  INTEGER
error_safe_message         TEXT
error_provider_request_id  TEXT
error_possibly_submitted   INTEGER
error_occurred_at          TEXT

created_at                 TEXT NOT NULL
updated_at                 TEXT NOT NULL
submitted_at               TEXT
completed_at               TEXT
```

约束：

- `revision >= 0`。
- `status` 只允许 `submitting/submitted/in_progress/succeeded/failed`。
- `prompt` 和 `model` 非空。
- 宽高为正整数。
- `provider_task_id` 非空时唯一。
- `submitting` 不得有 Provider Task ID。
- `submitted/in_progress/succeeded` 必须有 Provider Task ID。
- 时间使用 UTC RFC 3339 文本。
- SQLite 布尔值使用 `0/1/NULL`，Repository 映射为领域 bool。
- DomainError 字段要么整体为空，要么满足必要字段完整性。

索引：

```text
INDEX(status, updated_at DESC)
INDEX(updated_at DESC)
UNIQUE(provider_task_id) WHERE provider_task_id IS NOT NULL
```

不持久化：

- `result_ready`。
- `local_file_ready`。
- 图片数量。
- 聚合 Artifact 状态。
- next action。
- poll attempt、backoff 或 max attempts。

这些都由领域事实或应用策略派生。

## 11. generated_images 表

逻辑 schema：

```text
image_id                   TEXT PRIMARY KEY
job_id                     TEXT NOT NULL REFERENCES generation_jobs(job_id)
position                   INTEGER NOT NULL

provider_locator           TEXT NOT NULL
provider_metadata_json     TEXT

artifact_status            TEXT NOT NULL
artifact_key               TEXT
relative_path              TEXT
sha256                     TEXT
byte_size                  INTEGER
media_type                 TEXT
image_format               TEXT
width                      INTEGER
height                     INTEGER
saved_at                   TEXT

error_code                 TEXT
error_stage                TEXT
error_category             TEXT
error_retryable            INTEGER
error_retry_after_seconds  INTEGER
error_safe_message         TEXT
error_provider_request_id  TEXT
error_occurred_at          TEXT

created_at                 TEXT NOT NULL
updated_at                 TEXT NOT NULL
```

约束：

- 外键删除使用 `ON DELETE CASCADE`。
- `position >= 0`。
- `(job_id, position)` 唯一。
- `artifact_status` 只允许 `pending/available/failed`。
- `available` 必须具有完整 LocalArtifact 字段且没有当前 error。
- `pending/failed` 不得具有已承诺有效的 LocalArtifact 字段。
- `relative_path` 非空时唯一。
- `artifact_key` 非空时唯一。
- `sha256` 使用 64 位小写十六进制字符串。
- byte size、width 和 height 在非空时为正数。
- `provider_metadata_json` 只保存获取/诊断需要的最小结构，并带有独立内容版本字段。

不持久化：

- `downloading` 瞬时状态。
- 绝对路径。
- HTTP Content-Type 原始 Header。
- 聚合 partial/available 状态。
- 原始 Provider 图片对象。

## 12. artifact_cleanup_queue 表

正式 retention 删除涉及 SQLite 与文件系统，二者不能组成同一个原子事务。V1 使用清理队列表避免静默遗留不可追踪文件。

逻辑 schema：

```text
cleanup_id          TEXT PRIMARY KEY
job_id              TEXT NOT NULL
relative_job_dir    TEXT NOT NULL
attempts            INTEGER NOT NULL
last_error_message  TEXT
created_at          TEXT NOT NULL
updated_at          TEXT NOT NULL
```

retention 流程：

1. 在事务中选择过期终态 Job。
2. 为每个 Job 插入受控相对目录清理项。
3. 删除 Job；GeneratedImage 通过外键级联删除。
4. 提交事务。
5. 在事务外处理清理队列并删除受控产物目录。
6. 成功后删除 queue row；失败则增加 attempts 并保留待重试。

`relative_job_dir` 只能由 JobId 派生，不能存入任意用户路径。

## 13. Repository 事务边界

### 13.1 Submit

```text
事务：插入 submitting Job
提交事务
调用 ModelScope
事务：更新 ProviderTaskReference 与 JobStatus
提交事务
```

禁止事务跨越上游网络请求。

### 13.2 Check

```text
读取 Job + revision
事务外调用 ModelScope status
事务：基于 revision 保存合法状态变化
提交事务
```

### 13.3 Fetch

```text
读取 Job 和待处理图片
事务外下载、验证、原子保存图片
每张图片通过短事务提交状态与 LocalArtifact
```

多图片部分成功时不使用一个覆盖全部图片的回滚事务。

## 14. 并发控制

`generation_jobs.revision` 用于乐观并发。

更新形式：

```sql
UPDATE generation_jobs
SET ..., revision = revision + 1
WHERE job_id = ? AND revision = ?;
```

更新行数为零表示并发修改：

- 重新读取最新聚合。
- 如果目标操作已经由另一调用完成，则返回最新事实。
- 如果存在真正冲突，则返回 `CONCURRENT_MODIFICATION`。
- 不盲目覆盖较新状态。

同一进程维护 keyed AnyIO lock：

- 同一 Job 的 check/fetch 串行。
- 不同 Job 可并发。
- 同一次 fetch 内多图片受配置上限并发。
- lock registry 必须在 Job 不再被使用后释放条目，避免无界增长。

V1 不建设跨进程 lease。多个 MCP 服务进程共享同一 database/artifact root 不属于支持场景。

## 15. Artifact Store 目录结构

```text
artifact_root/
└── jobs/
    └── <job_id>/
        ├── 000-<image_id>.png
        ├── 001-<image_id>.jpg
        └── .tmp/
```

规则：

- Job directory 只由规范 JobId 生成。
- 最终文件名只由 position、ImageId 和验证后的实际格式生成。
- position 使用固定宽度十进制表示以便排序。
- 不使用 prompt、远程 URL、Content-Disposition 或用户输入生成文件名。
- 扩展名来自 Pillow 验证结果的受控格式映射。
- 临时文件与最终文件位于同一文件系统。
- 临时文件使用不可预测名称和 `.part` 后缀。
- V1 不允许 Agent 指定 output directory、绝对路径或最终文件名。

逻辑 ArtifactKey：

```text
jobs/<job_id>/images/<image_id>
```

ArtifactKey 与相对文件路径相关但不等同，未来可以在不改变领域身份的情况下调整物理布局。

## 16. 图片下载与原子提交

单张图片流程：

1. 在受控 `.tmp` 目录创建临时文件。
2. 通过 HTTPX 流式写入。
3. 在读取过程中累计字节数和 SHA-256。
4. 超过 `MAX_DOWNLOAD_BYTES` 立即中止并删除临时文件。
5. 关闭写入句柄。
6. 使用 Pillow 验证真实格式、媒体类型、宽度和高度。
7. 应用 `MAX_IMAGE_PIXELS`。
8. 根据验证格式计算最终相对路径。
9. 再次验证最终路径位于 artifact root。
10. 原子移动临时文件到最终路径。
11. 创建 LocalArtifact 并通过短事务保存为 available。

默认保存原始下载字节，不重新编码。

如果数据库保存 LocalArtifact 失败但文件已经原子提交：

- 保留文件。
- 返回持久化错误。
- 后续 fetch 可以检测确定路径下的有效文件，重新验证并修复元数据。
- 不因为数据库暂时失败删除已经完整生成的用户产物。

## 17. 路径安全

任何 ArtifactKey 或相对路径解析都必须：

1. 使用已解析的 artifact root。
2. 拒绝绝对路径、盘符、UNC 注入和空路径组件。
3. 拒绝 `.`、`..` 和平台分隔符注入。
4. 拼接受控组件。
5. 规范化候选路径。
6. 验证候选路径仍位于 artifact root 内。
7. 检查路径链中的已有组件不是符号链接或重解析点逃逸。
8. 最终文件提交前再次验证。

Artifact Store 不接受 MCP 原始字符串路径；它接受 JobId、ImageId、position 和受控图片格式。

## 18. MCP 路径可见性

- 领域和数据库只保存相对路径。
- `fetch_image_generation_result` 可以为 available 图片返回解析后的绝对本地路径。
- 单任务完整结果可以返回 available 图片绝对路径。
- `list_image_generations` 不返回绝对路径。
- Provider locator 不作为普通结果路径返回。
- 未来增加 MCP Resource URI 时，从 ArtifactKey 派生，不修改领域或数据库主键。

## 19. 正式数据保留

默认：

```text
TERMINAL_JOB_RETENTION_DAYS = 0
```

即不自动删除正式 Job 或图片。

启用 retention 后：

- 只选择 `succeeded/failed` Job。
- 根据 `updated_at` 判断过期。
- 永不自动删除 `submitting/submitted/in_progress`。
- 分批处理，避免长事务。
- 元数据删除和文件删除通过 artifact_cleanup_queue 衔接。
- 清理只能删除 `artifact_root/jobs/<valid-job-id>`。
- 清理失败不阻止服务运行，并在后续维护周期重试。

V1 不提供 MCP 删除工具。操作者通过配置控制自动清理，或在服务停止后自行管理数据目录。

## 20. 临时文件清理

默认：

```text
TEMP_FILE_RETENTION_HOURS = 24
```

启动和维护清理：

- 只扫描本系统 Job 目录内的 `.tmp`。
- 只删除超过期限且匹配内部临时文件格式的普通文件。
- 不跟随符号链接。
- 不删除最终图片。
- 单个文件失败记录警告并继续。
- 正在当前进程 fetch 的临时文件通过进程内注册表排除。

## 21. 启动恢复

启动顺序：

1. 解析并校验非 Token 配置。
2. 创建受控数据目录和 artifact root。
3. 打开 SQLite，应用 PRAGMA。
4. 校验/迁移 schema。
5. 查找遗留 `submitting` Job。
6. 将其转换为 `failed + SUBMISSION_OUTCOME_UNKNOWN + possibly_submitted=true`。
7. 清理过期临时文件。
8. 如果 retention 已启用，分批安排过期终态 Job 清理。
9. 处理 artifact cleanup queue。
10. 开始接受 MCP 请求。

启动时不：

- 批量轮询 submitted/in_progress Job。
- 批量下载 succeeded Job 图片。
- 自动重试 submitting Job。
- 因 Token 缺失而拒绝启动。

失败策略：

- schema 版本、迁移或数据库打开失败：拒绝启动。
- 必要目录不可用：拒绝启动。
- 单个临时文件或 retention 清理失败：记录警告并继续。
- cleanup queue 单项失败：保留队列项并继续。

## 22. 数据库备份与维护边界

V1 不内置备份工具。

文档必须说明：

- 复制 SQLite 数据时需要包含主文件以及一致性要求，推荐在服务停止后备份。
- artifact root 和 database 应作为一个逻辑数据集备份。
- 直接编辑数据库不受支持。
- 删除数据库不会自动删除 artifact root。
- 删除 artifact root 会造成 metadata 指向缺失文件，后续 fetch 可以尝试恢复非 available 或缺失产物。

## 23. 配置错误行为

启动阶段静态配置错误：

- 非法 URL。
- 非法路径类型。
- 负数或零安全上限。
- 无法打开数据库。
- 无法创建必要目录。

这些错误写入 stderr 并拒绝启动。

运行阶段配置错误：

- 缺少 ModelScope Token。

它通过需要上游的工具返回稳定结构化错误，不终止服务。

## 24. 验收场景

至少覆盖：

1. 默认目录不受当前工作目录变化影响。
2. Token 缺失时服务可启动并列出本地任务。
3. Token 缺失时 submit/check 返回稳定配置错误。
4. 新数据库创建 schema version 1。
5. 高版本数据库拒绝启动。
6. 迁移失败完整回滚。
7. submitting Job 在重启后转为提交结果不确定失败。
8. Job 和多图片聚合可完整 round-trip。
9. 派生布尔值和聚合状态不进入数据库。
10. revision 冲突不覆盖较新状态。
11. 同一 Job 并发 fetch 不重复提交产物。
12. 不同 Job 可以并发处理。
13. 下载超过字节上限时清理临时文件。
14. 图片超过像素上限时不提交最终文件。
15. 内容格式与扩展名来自实际验证。
16. prompt 和 locator 不出现在列表或日志。
17. 路径遍历、绝对路径、符号链接逃逸和 Windows 路径注入被拒绝。
18. 数据库提交失败后，完整文件可以在后续 fetch 中修复元数据。
19. retention 不删除活动 Job。
20. cleanup queue 可以重试失败的文件删除。
21. 临时文件清理不删除最终图片或活跃临时文件。
22. list 不返回绝对路径，fetch 为 available 图片返回绝对路径。

## 25. 后续文档约束

- `05-mcp-interface-contract.md` 不得暴露 output directory 或 output filename 参数。
- `05` 的工具参数不得覆盖下载字节、像素和并发安全上限。
- `05` 的列表输出不得包含 prompt、Provider locator 或绝对路径。
- `05` 可以在 fetch 和单任务完整结果中返回 available 图片的绝对路径。
- `06-core-organization.md` 必须把 Settings、SQLite Repository 和 Artifact Store 放在领域边界之外。
- `08-implementation-brief.md` 必须包含迁移、路径逃逸、WAL、revision、原子保存和启动恢复测试。
