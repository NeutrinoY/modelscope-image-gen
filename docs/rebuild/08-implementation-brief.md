# ModelScope Image Gen MCP 重构实施简报

## 文档状态

- 状态：已确认
- 前置文档：00-rebuild-direction.md 至 07-agent-experience.md
- 适用目标：重构后的 V1
- 目标开发版本：0.2.0
- 执行方式：测试驱动的纵向切片重建

本文是执行 Agent 的入口文档。执行者必须先完整阅读本文，再按本文索引追溯 00–07。本文压缩目标、不可偏离的决策、归档边界、实施阶段、质量门禁和完成定义，不替代各专项契约。

实施不是旧代码迁移或技术栈换壳。实施目标是将已验证的业务语义翻译为新的领域模型、应用用例、基础设施端口和 MCP v2 契约。

## 1. 一句话目标

将当前 0.1.0 实现归档为只读语义与反例资产，从空白根目录重建一个 Python 3.14、uv、MCP v2、ModelScope 专用、本地优先、可恢复、支持多图片领域契约的文生图 MCP Server。

## 2. 详细文档索引

| 文档 | 权威范围 |
|---|---|
| 00-rebuild-direction.md | 产品边界、资产角色、继承与禁止事项 |
| 01-product-and-information-architecture.md | 五工具、默认工作流、用户角色和信息层级 |
| 02-technology-stack-decisions.md | Python、uv、MCP v2、依赖、质量与发布工具 |
| 03-domain-model-and-behavior-map.md | 聚合、状态机、错误、多图和旧行为映射 |
| 04-config-and-storage-schema.md | 配置、SQLite、目录、并发、保留和恢复 |
| 05-mcp-interface-contract.md | wire schema、ToolContract、错误、annotations 和分页 |
| 06-core-organization.md | 包结构、端口、适配器、依赖方向和测试组织 |
| 07-agent-experience.md | 工具描述、TextContent、日志、文档与 Host 体验 |

冲突处理顺序：

1. 先确认是否只是不同文档描述不同层级的同一事实。
2. 如果确有冲突，停止相关实现。
3. 回到拥有该事实权威范围的文档修订并获得确认。
4. 不通过代码中的临时兼容同时实现两种语义。

本文不得被解释为静默覆盖 00–07。

## 3. 已锁定的产品边界

V1 包含：

- 文本生成图片。
- ModelScope 单一 Provider。
- submit_image_generation、check_image_generation、fetch_image_generation_result、list_image_generations 和 generate_image 五个工具。
- 默认异步 submit → check → fetch。
- 本地 SQLite Job 恢复与发现。
- 受控本地 Artifact Store。
- 一次任务零到多张结果的领域表达；成功 Job 至少一张。
- stdio MCP v2。
- PyPI/uvx 分发。

V1 不包含：

- 图生图、编辑或参考图片。
- 多 Provider 或插件发现。
- Web/桌面 UI。
- Streamable HTTP。
- OAuth、多租户或远程服务控制面。
- 上游取消，除非真实 ModelScope 契约另行证明并重新决策。
- MCP v1 兼容。
- Prompts、Resources、Completions 或 experimental Tasks。
- Agent 可调用的删除或清理工具。
- 旧 JSON Job 迁移。

## 4. 已锁定的技术栈

目标：

~~~text
Python                  >=3.14,<3.15，标准 GIL
uv                      >=0.11.28,<0.12
build backend           uv_build
MCP SDK beta 阶段       mcp==2.0.0b1
HTTP                    httpx>=0.28.1,<1
async API               anyio>=4.14,<5，asyncio backend
validation              pydantic>=2.13.4,<2.14
settings                pydantic-settings>=2.14,<3
database                aiosqlite>=0.22,<1
directories             platformdirs>=4,<5
image validation        Pillow>=12.3,<13
tests                   pytest>=9,<10 + AnyIO plugin
format/lint             Ruff
types                   ty==0.0.58
~~~

不得加入与上述职责重复的框架。MCP v2 或 ty 升级必须是独立变更，并运行完整回归。

## 5. 当前 0.1.0 基线

2026-07-10 重新验证：

~~~text
branch: main
commit: 42c0709
package version: 0.1.0
tests: 28 passed
ruff check: passed
runtime target: Python >=3.12
resolved MCP: 1.26.0
storage: per-job JSON files
public tools: 4
~~~

旧实现的可继承语义：

- prompt、negative_prompt、seed、model、size。
- ModelScope 异步提交、状态查询和图片获取。
- submit/status/download 分阶段 HTTP timeout。
- Retry-After、request ID、retryable 和阶段错误经验。
- Agent 默认使用异步长任务工作流。
- Job 需要跨 MCP 调用和进程重启恢复。
- octet-stream 仍需按真实图片内容验证。
- 阻塞便利入口有价值。

旧实现的反例：

- import 阶段创建全局 Settings、Service 和 Server 资源。
- Mixin 组合的 ImageGenerationService。
- MCP 类型贯穿工作流。
- dict[str, Any] 充当领域对象。
- 每 Job 一个 JSON 文件。
- timeout 作为 Job 终态。
- 只保存 output_images[0]。
- 模型控制 output directory 和 filename。
- 文本镜像完整 JSON。
- 日志记录 prompt 和图片 URL。
- 每次调用创建 HTTP Client。
- 手写 schema、工具名 if/elif 分发和旧接口 alias。

旧测试是行为证据，不是新接口兼容要求。

## 6. Git 与版本准备

实施前按顺序执行：

1. 确认工作区只有本次 docs/rebuild 文档变更和已知用户文件。
2. 在 commit 42c0709 上创建 annotated tag：legacy/v0.1.0。
3. 从 main 创建分支：rebuild/v0.2.0。
4. 将 00–08 作为独立设计文档提交。
5. 再执行 legacy 归档并形成独立提交。
6. 后续每条纵向能力独立提交。

建议提交信息：

~~~text
docs: define rebuild contract
chore: archive v0.1.0 implementation
build: establish Python 3.14 project foundation
feat: implement submit generation slice
feat: implement status and recovery slices
feat: implement artifact fetch slice
feat: compose blocking generation workflow
docs: complete agent and operator experience
ci: complete release verification
~~~

规则：

- 不直接在 main 上开始搬迁。
- 不重写或强制移动历史。
- 不使用 git reset --hard 清理工作区。
- 不把依赖升级、业务能力和全仓格式化混进一个提交。
- 不在未通过相应阶段门禁时提交“完成”声明。

## 7. Legacy 归档

归档目标：

~~~text
legacy/v0.1.0/
~~~

归档只保留有语义或反例价值的最小资产：

~~~text
main.py
README.md
README.zh-CN.md
src/modelscope_image_gen/
.github/workflows/ci.yml
tests/service_test_helpers.py
tests/test_client.py
tests/test_server_errors.py
tests/test_service_async_flow.py
tests/test_service_generate_errors.py
tests/test_service_generate_outputs.py
tests/test_service_generate_polling.py
~~~

这些测试覆盖旧上游请求、异步 submit/status/result、结构化错误、敏感字段净化、图片内容处理和阻塞轮询经验。它们是只读行为证据，不在 legacy 中继续运行。

不移动：

~~~text
.git/
docs/rebuild/
~~~

不作为归档资产提交：

~~~text
.github 其他文件
.gitignore
.python-version
pyproject.toml
uv.lock
tests/conftest.py
tests/test_config.py
tests/test_task_store.py
.venv/
.ruff_cache/
__pycache__/
outputs/
.DS_Store
.env
Token
运行时 Job 数据
生成图片
~~~

被忽略的本地运行产物不因归档自动删除或移动；除非操作者明确要求，否则保留在用户工作区之外的现状。

新增 legacy/README.md，至少记录：

- 来源 commit 与 annotated tag。
- 包版本和验证日期。
- 28 项测试、Ruff 基线。
- 旧启动和测试方式。
- 可继承的业务语义。
- 禁止继承的技术结构。
- legacy 不属于根 uv project。
- 新代码禁止 import legacy。
- 完整旧依赖、构建配置和未筛选文件从 legacy/v0.1.0 Git tag 查看。

Legacy 是最小语义归档，不是可独立安装的旧项目副本。旧 CI 仅用于理解历史质量基线；legacy 不参与任何根项目命令。

## 8. 新根目录起点

归档提交之后，受版本控制的根项目源文件只保留：

~~~text
.git/
docs/
legacy/
~~~

以及 Git 所需的最小元数据。随后重新创建：

~~~text
.github/
.gitignore
.python-version
pyproject.toml
uv.lock
README.md
README.zh-CN.md
LICENSE
SECURITY.md
CHANGELOG.md
src/
tests/
~~~

新文件不得通过复制 legacy 整棵目录产生。允许对单个旧行为进行重新实现，但必须先找到对应 00–07 契约和新测试。

## 9. 总体执行策略

采用测试驱动的纵向切片：

~~~text
失败测试
→ 最小领域行为
→ 应用用例
→ 端口与基础设施适配器
→ MCP ToolContract
→ 内存 Client 验证
→ 全部门禁
→ 重构
~~~

每个切片必须：

- 穿过真实目标层次。
- 返回稳定的新契约。
- 不创建未来占位实现。
- 不暴露 NOT_IMPLEMENTED 工具给真实 Host。
- 在本阶段需要的范围内保持 package 可导入、测试可运行、wheel 可构建。

开发中未完成的工具可以暂不进入运行时 registry；发布验收时 registry 必须固定注册全部五个工具且顺序正确。禁止注册返回假成功或无结构占位错误的空壳工具。

## 10. 阶段 0：归档与工程基础

### 10.1 交付

- Git tag、重构分支和 legacy 归档。
- Python 3.14 .python-version。
- 新 pyproject.toml 和 uv.lock。
- uv_build 与 src layout。
- 轻量 package init、cli、__main__、bootstrap。
- importlib.metadata 版本读取。
- Pydantic Settings 和 platformdirs 路径解析。
- stderr logging 最小配置。
- 测试目录和 AnyIO asyncio fixture。
- Ruff、ty 和 pytest 配置。
- Windows/Ubuntu GitHub Actions。
- 标准库 AST 架构测试。
- 最小 wheel 安装与 --version 测试。

### 10.2 最小运行要求

- package import 不读取 Settings、不创建目录、不打开数据库。
- cli --version 不需要 Token。
- Token 缺失不阻止后续 Server 启动设计。
- stdio stdout 不出现日志。
- legacy 不在构建产物、测试发现、Ruff 或 ty 范围内。

### 10.3 出口

~~~text
uv lock --check
uv sync --locked --all-groups
uv run ruff format --check
uv run ruff check
uv run ty check
uv run pytest
uv build --no-sources
~~~

wheel 内容审计确认不包含 legacy。

## 11. 阶段 1：Submit 第一条完整纵向切片

### 11.1 Domain

定义 03 文档中的稳定聚合结构，并首先实现 submit 所需行为：

- JobId、ImageId、ProviderName。
- GenerationRequest、ImageSize。
- JobStatus。
- ProviderTaskReference。
- ProviderImageReference、GeneratedImage、ArtifactStatus 和 LocalArtifact 的稳定类型与不变量。
- GenerationJob submitting/submitted/failed 不变量。
- DomainError 与提交阶段 code。
- Clock 和 IdentifierFactory 端口。

这些类型是 GenerationJob 固定结构的一部分，不是未来占位。阶段 1 不实现 check/fetch 应用用例，也不为后续切片预写空方法。

### 11.2 Application

实现：

- OperationResult。
- ApplicationError 和安全恢复上下文。
- SubmitGeneration。
- ImageGenerationProvider.submit。
- GenerationJobRepository.add/get/save。
- NextStep CHECK。

正确时序：

~~~text
validate request
→ create submitting Job
→ persist
→ call ModelScope
→ apply submission outcome
→ persist submitted or failed
~~~

### 11.3 Infrastructure

实现：

- SQLite connection、schema version 1 和初始 migration。
- 初始 migration 一次性创建 04 锁定的 generation_jobs、generated_images、artifact_cleanup_queue、索引和约束；不能先发布 submit 专用 schema 再无版本修改。
- generation_jobs 的 submit 路径映射；其他表在后续切片开始使用。
- HTTPX lifespan client。
- ModelScope submit schema、mapping 和 error mapping。
- submitting 启动恢复。

外部请求不能位于 SQLite transaction 中。

### 11.4 MCP

实现：

- Submit input/output Pydantic DTO。
- ToolEnvelope、ErrorOutput、JobOutput、NextActionOutput 的完整稳定 wire 字段；阶段 1 只产生 submit 相关状态和值，不能发布后续需要破坏性扩展的临时 output schema。
- ToolContract 验证链。
- submit description、annotations 和 TextContent。
- 低层 Server Tools-only 接线。

### 11.5 关键测试

- 外部调用前已持久化 submitting。
- 成功获得 Task ID 后转 submitted。
- 明确拒绝转 failed，possibly_submitted=false。
- 响应前连接中断转 SUBMISSION_OUTCOME_UNKNOWN。
- 结果不确定不自动重试。
- 重启遗留 submitting 转结果不确定失败。
- Token 缺失返回 MODELSCOPE_TOKEN_MISSING，但 Server 可启动。
- schema、is_error、TextContent 和敏感信息契约。

## 12. 阶段 2：Check、恢复与 List

### 12.1 Check

实现：

- ProviderPending、ProviderRunning、ProviderSucceeded、ProviderFailed 和 ProviderUnknownStatus。
- submitted/in_progress/succeeded/failed 状态转换。
- 每次 check 最多一次上游查询。
- terminal Job 只读本地事实。
- 网络、HTTP、解析和未知状态时保持 Job 状态。
- 成功零图片转 EMPTY_OUTPUT_IMAGES。
- 多图片生成稳定 ImageId 和 position。

### 12.2 Repository 与并发

实现：

- 完整 Job + GeneratedImage round-trip。
- revision 乐观并发。
- keyed AnyIO Job lock。
- 同 Job 串行、不同 Job 并发。
- lock registry 生命周期清理。
- WAL、foreign_keys、synchronous 和 busy_timeout。

### 12.3 List

实现：

- JobSummaryView。
- status filter。
- limit 1..100。
- updated_at DESC、job_id DESC keyset pagination。
- 版本化 base64url cursor。
- filter fingerprint。
- INVALID_CURSOR。
- 不加载或返回 prompt、locator、路径和完整图片。

### 12.4 出口场景

- Server 重启后能通过 Job ID 继续 check。
- Agent 丢失 Job ID 后能通过 list 恢复。
- list 不批量访问 ModelScope。
- failed Job 的成功 check 使用 ok=true/is_error=false。
- 未知 Provider 状态不变成 in_progress 或 failed。

## 13. 阶段 3：Fetch 与 Artifact Store

### 13.1 领域与用例

实现：

- GeneratedImage、ArtifactStatus 和 LocalArtifact。
- 聚合 artifact status 派生。
- FetchGenerationResult。
- 多图独立结果和部分成功。
- available 图片幂等跳过。
- pending/failed 图片可重试。

### 13.2 Artifact Store

实现：

- 受控 ArtifactKey 和相对路径。
- jobs/<job_id>/... 物理布局。
- 同文件系统临时目录。
- HTTP 流式下载。
- 最大字节限制。
- SHA-256。
- Pillow 解码、格式、媒体类型、尺寸和像素上限。
- 保存原始下载字节。
- 验证后受控扩展名。
- 原子提交。
- 失败临时文件清理。
- 已存在有效文件的元数据修复。

### 13.3 路径安全

测试：

- 绝对路径注入。
- ../ 和空组件。
- Windows 盘符和 UNC。
- 混合分隔符。
- 符号链接。
- Windows reparse point。
- 最终提交前路径二次验证。

Artifact Store 只接收受控值对象，不接收 MCP 原始路径字符串。

### 13.4 清理

实现：

- artifact_cleanup_queue。
- 临时文件 24 小时默认清理。
- terminal retention 默认关闭。
- 正式清理只处理 terminal Job。
- 清理失败可重试且不阻止启动。

### 13.5 出口场景

- 单图和多图全部成功。
- 多图部分成功。
- 第一次下载失败、第二次成功。
- available 图片不重复下载。
- 取消后保留已原子提交图片。
- 数据库提交失败后可以修复文件元数据。
- fetch 返回全部 available 绝对路径。

## 14. 阶段 4：Blocking Generate

GenerateImage 只能组合已完成的：

~~~text
SubmitGeneration
CheckGeneration
FetchGenerationResult
~~~

实现：

- max_wait_seconds null 使用服务器默认。
- wire 范围 1..3600。
- AnyIO timeout/cancel scope。
- Waiter 端口。
- 服务器统一 poll interval。
- 到达预算时 completed=false。
- 返回 Job ID、当前状态和 CHECK next action。
- succeeded 后调用同一个 fetch 用例。

禁止：

- 独立 submit/poll/download 实现。
- 在 Job 中保存 poll attempt。
- 暴露 poll interval、attempts 或 backoff 参数。
- 将本地等待到期写成 Job timeout。
- 将调用取消写成上游 canceled。

## 15. 阶段 5：Agent 与操作者体验

实现 07 的完整契约：

- Server name、title、version 和 instructions。
- 五工具最终固定顺序。
- description 与 annotations。
- 确定性 TextContent。
- fetch/generate 路径列表。
- list 紧凑行与 cursor。
- SUBMISSION_OUTCOME_UNKNOWN 防重提文本。
- stderr key=value 日志。
- 稳定 event taxonomy。
- 敏感信息哨兵测试。

文档交付：

~~~text
README.md
README.zh-CN.md
CHANGELOG.md
SECURITY.md
LICENSE
~~~

README 首先介绍异步工作流，阻塞 generate 置于次级位置。

## 16. 阶段 6：发布级验证

完成：

- 官方 MCP 内存 Client 全契约测试。
- MCP Inspector 人工检查。
- Windows 与 Ubuntu stdio 子进程。
- 从 wheel 安装后重复 CLI/stdio 测试。
- migration SQL/package data wheel 测试。
- sdist/wheel 内容审计。
- 至少两个真实 MCP Host，其中至少一个 Windows Host。
- 显式启用的真实 ModelScope submit/check/fetch 样本。
- MCP Registry server.json 生成和校验。
- GitHub Actions Trusted Publishing 配置。

正式发布前若 MCP v2 stable 已发布：

1. 创建独立依赖升级变更。
2. 将 mcp beta pin 切换为经验证的 >=2.0,<3 范围。
3. 重新检查 API、capability、schema、is_error 和 Client 行为。
4. 运行全部单元、集成、契约、E2E、Host 和 live 验证。
5. 不在同一变更中升级 Pydantic 或修改领域契约。

## 17. 测试驱动规则

每个行为先有能够失败的测试。

测试层：

1. unit/domain：纯标准库，不触碰网络、SQLite 或真实文件持久化。
2. unit/application：内存 ports、fake Clock/IDs/Waiter。
3. integration/modelscope：HTTPX MockTransport + 脱敏 fixture。
4. integration/sqlite：临时数据库、迁移、事务、revision、重启。
5. integration/artifacts：临时 root、真实 Pillow、路径攻击。
6. contract/mcp：官方内存 Client。
7. e2e/stdio：真实 console script 子进程。
8. e2e/wheel：从 wheel 安装。
9. live/modelscope：显式 opt-in。

Live 测试约定：

~~~text
MODELSCOPE_IMAGE_GEN_RUN_LIVE_TESTS=1
MODELSCOPE_SDK_TOKEN=<operator-provided-secret>
~~~

没有 opt-in 或 Token 时 live 测试必须 skip，不得失败，也不得产生外部请求。

## 18. ModelScope 事实证据

Provider 实现必须建立脱敏 fixture：

- submit success。
- submit reject。
- status pending/running/succeed/failed。
- success one image。
- success multiple images，若真实 API 能产生。
- success empty image list。
- unknown status。
- malformed response。
- 429 + Retry-After。
- request ID。
- image response with image/*。
- image response with application/octet-stream。
- invalid image bytes。

Fixture 规则：

- 标明来自真实响应、官方文档还是合成边界测试。
- 删除 Token、签名 URL、Cookie、完整 prompt 和个人标识。
- 不保存完整无关 response。
- 影响控制流的字段必须有证据。
- 多图若无法通过真实模型验证，仍测试领域/契约能力，但文档不得宣称上游已保证多图。

## 19. 每阶段质量门禁

基础门禁：

~~~text
uv lock --check
uv sync --locked --all-groups
uv run ruff format --check
uv run ruff check
uv run ty check
uv run pytest
uv build --no-sources
~~~

附加门禁：

- MCP 变更：内存 Client 和 schema snapshot。
- SQLite 变更：migration、round-trip、restart 和 concurrency。
- Artifact 变更：Windows/Posix 路径与真实图片 fixture。
- Package data 变更：wheel 安装。
- CLI/logging 变更：stdio stdout/stderr 分离。
- Provider 契约变更：MockTransport fixture；发布候选需要 live。

不得用跳过测试、宽泛 ignore 或放宽 schema 使门禁变绿。

## 20. 类型与代码质量

- ty 是唯一类型检查器。
- 不增加 Pyright 或 mypy 配置。
- 不使用大范围 type ignore。
- 第三方类型问题通过窄适配边界或有说明的局部抑制处理。
- 不使用 Any 连接 Domain、Application 和 Infrastructure。
- Provider outcome 使用封闭类型。
- Domain 使用 frozen、slots dataclass 和 StrEnum。
- MCP DTO 使用 Pydantic。
- 模块超过约 300 行时检查职责，不机械拆文件。
- 不创建 utils.py、helpers.py 或无边界 service.py。

## 21. 架构门禁

AST 测试至少阻止：

- Domain 导入 Pydantic、MCP、HTTPX、aiosqlite、Pillow 或 platformdirs。
- Application 导入 Infrastructure 或 MCP adapter。
- MCP adapter 导入具体 Infrastructure。
- 新代码导入 legacy。
- bootstrap 之外同时认识具体 Infrastructure 与 MCP adapter。
- import 阶段执行 Settings 解析、数据库打开、HTTP Client 创建或 migration。

代码审查还要确认：

- MCP handler 不写 SQL、HTTP 或文件。
- Provider 不写 SQLite 或 Artifact。
- Artifact Store 不下载 URL 或更新 Job。
- Repository 不解释 Provider response。
- Presenter 不执行业务判断。

## 22. 数据与安全门禁

必须验证：

- Token 不进入 SQLite、日志、TextContent 或错误。
- prompt 不进入列表和默认日志。
- Provider locator 不进入列表、普通文本和日志。
- stdout 只有 MCP wire。
- Agent 不能指定 output directory、绝对路径或 filename。
- 临时与最终文件都在 artifact root 内。
- 数据库、WAL、SHM 和 artifact root 被文档标为敏感数据。
- wheel/sdist 不包含数据库、图片、.env、legacy 或 fixture secrets。

敏感信息测试使用唯一哨兵字符串，并同时捕获 structured content、TextContent、stderr 和构建产物。

## 23. 完成度评估

每个维度使用：

~~~text
未开始
骨架
可运行
可用
可靠
可发布
~~~

发布候选评估：

| 维度 | 最低要求 |
|---|---|
| 方向一致性 | 可发布 |
| 技术栈一致性 | 可发布 |
| 领域模型 | 可发布 |
| submit/check/list/fetch | 可发布 |
| blocking generate | 可发布 |
| SQLite/恢复/并发 | 可发布 |
| Artifact/路径安全 | 可发布 |
| MCP 契约与 Agent 体验 | 可发布 |
| 文档 | 可发布 |
| 真实 Host | 可发布 |
| 真实 ModelScope 样本 | 可靠 |
| Registry/PyPI 发布配置 | 可用；实际发布可由操作者决定 |

“代码存在”只等于骨架或可运行，不得报告为完成。

## 24. 实现 Agent 的自由与边界

允许：

- 在不改变职责的前提下机械调整模块文件名。
- 提取小型明确策略对象。
- 增加能证明契约的测试。
- 使用标准库改善内部实现。
- 在已确认版本范围内由 uv 解析兼容补丁版本。
- 对内部私有类型做不影响 wire/领域的调整。

需要先修订文档并获得确认：

- 工具增删或重命名。
- 输入输出 schema 改变。
- Error code、JobStatus 或 ArtifactStatus 改变。
- Provider、数据库、异步模型或构建工具改变。
- 允许 Agent 控制路径。
- 旧数据迁移。
- MCP Resources/Prompts、HTTP transport 或认证。
- 上游取消、多 Provider、图生图或编辑。

禁止为了快速实现改变边界。

## 25. 明确禁止事项

- 不逐行翻译 legacy。
- 不复制 Mixin Service。
- 不保留 compatibility alias。
- 不使用 MCP v1。
- 不使用高层 MCPServer。
- 不裸用低层 Server 手写重复 schema。
- 不将 MCP DTO 当领域对象。
- 不将 SQLite row 当领域对象。
- 不让原始 ModelScope dict 驱动状态机。
- 不把 timeout 写入 JobStatus。
- 不假设单图片。
- 不自动重试可能已提交的 submit。
- 不在数据库事务内访问网络或 Pillow。
- 不返回 base64 ImageContent。
- 不引入 ORM、队列、Tenacity、structlog、OpenTelemetry 或重复质量工具。
- 不让 legacy 参与 root project。
- 不在没有真实证据时宣称 ModelScope 取消、多图或 URL 永久有效。

## 26. 最终完成定义

只有全部满足时，重构才完成：

1. 00–07 的确认契约全部落实。
2. 五工具按固定顺序公开并通过 schema/annotations snapshot。
3. submit/check/fetch 默认路径真实可用。
4. list 能在丢失 Job ID 和重启后恢复工作流。
5. generate 复用异步用例并能超时交接。
6. 一次任务完整表达 list[GeneratedImage]。
7. 多图部分成功和重复 fetch 幂等。
8. submitting 崩溃窗口安全恢复。
9. SQLite migration、WAL、revision 和并发锁通过。
10. Artifact 字节、像素、格式、路径和原子保存通过。
11. Windows 和 Ubuntu 门禁通过。
12. Ruff、ty、pytest、build 和 wheel 安装通过。
13. MCP 内存 Client、Inspector 和至少两个真实 Host 通过。
14. 至少一个显式 ModelScope live 样本通过。
15. stdout 无日志污染，敏感信息哨兵测试通过。
16. README 双语、LICENSE、SECURITY、CHANGELOG 和 server.json 完整。
17. wheel/sdist 不包含 legacy 或运行时敏感产物。
18. legacy/v0.1.0 可独立追溯，但新代码没有任何依赖。

如果 live 样本、真实 Host 或某个平台未验证，必须明确报告为“可运行/可用但未达到可靠或可发布”，不能用单元测试替代完成声明。

## 27. 执行入口清单

实现 Agent 开始前：

1. 阅读本文。
2. 阅读 00 和 03，理解语义与状态机。
3. 阅读当前阶段对应的专项文档。
4. 检查 Git branch、status、tag 和用户已有变更。
5. 运行并记录旧 0.1.0 基线。
6. 完成归档，不删除用户本地运行数据。
7. 为当前切片写失败测试。
8. 只实现当前阶段需要的最小完整能力。
9. 运行相应门禁。
10. 更新完成度，不夸大未验证能力。

第一条代码切片必须是 submit。最后一个功能切片必须是 blocking generate；发布与 Host 加固在其后完成。

## 28. 交付报告

每个阶段交付报告至少包含：

- 完成的领域/工具能力。
- 关键文件。
- 执行的验证命令与结果。
- live/Host 是否实际运行。
- 尚未达到的完成度。
- 已知风险。
- 是否改变任何文档契约。

最终报告必须区分：

- 自动化测试通过。
- wheel 实际安装通过。
- 真实 Host 通过。
- 真实 ModelScope 通过。
- PyPI/Registry 配置完成。
- 是否实际发布。

配置完成不等于已经发布，MockTransport 通过不等于真实 API 已验证。
