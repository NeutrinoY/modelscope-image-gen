# ModelScope Image Gen MCP 项目维护与交接手册

> 状态：当前维护基线<br>
> 适用范围：根项目 `0.2.1` 及其后续演进，不适用于 `legacy/v0.1.0` 的内部维护<br>
> 实现复核基线：`9f48993`（2026-07-12）<br>
> 维护责任：任何改变产品语义、架构边界、公开契约、数据或验证方式的变更，都必须同步复核本文

## 1. 本手册的角色

本手册是重构完成后，后续 Agent 和总开发者维护当前项目的统一入口。它不复述所有源码，也不把 `docs/rebuild` 压缩成另一份历史设计稿。它负责回答：

- 当前系统真正维护哪些事实；
- 一次操作如何穿过完整系统；
- 每一层拥有和不拥有哪类知识；
- 哪些性质必须长期保持；
- 当前实现可以怎样演进，哪些变化必须先形成正式决策；
- 修改某类能力时需要检查哪些全局影响；
- 如何延续当前代码风格、可靠性标准和 Agent 体验；
- 如何证明变更没有造成局部正确、全局漂移；
- 如何把本次会话的新认知继续交给下一任 Agent。

本文采用[面向会话型 Agent 的长期项目连续性元指南](../agent-project-continuity-meta-guide.md)中的规范用语、全局优先工作流、独立判断责任和交接原则。本文未说明的通用治理问题，以该元指南为准；本文负责将其具体化到 ModelScope Image Gen MCP。

### 1.1 非目标

本文不承担以下职责：

- 用户安装和工具使用说明：见[中文 README](../../README.zh-CN.md)和[英文 README](../../README.md)；
- 完整 wire 字段参考：以 MCP Pydantic DTO、契约测试和重构接口文档为事实源；
- 逐项环境变量参考：以 `Settings`、`.env.example` 和 README 为事实源；
- 0.2 重构执行计划：见 [`docs/rebuild/08-implementation-brief.md`](../rebuild/08-implementation-brief.md)；
- 0.1 代码维护：`legacy/` 是只读历史资产；
- 提交与版本变化：日常提交见 Git 历史，面向发布的变化和兼容边界见 [CHANGELOG](../../CHANGELOG.md)。

### 1.2 新鲜度规则

页首基线表示本文最后一次与实现整体交叉复核的位置，不表示后续代码自动正确。任何语义性变更完成时，维护者应该：

1. 检查本文受影响章节；
2. 更新当前实现描述、变更路径或不变量；
3. 必要时更新基线版本、提交或复核日期；
4. 删除或明确标记已经被取代的内容；
5. 保持历史重构文档原貌，通过新决策建立取代关系。

### 1.3 按任务阅读

本文首次接手时应完整阅读；熟悉项目后的日常维护可以按任务快速回查：

| 任务 | 优先章节 |
|---|---|
| 第一次接手 | 2–10，再阅读任务对应的 11–14 |
| 修复缺陷 | 5–7、10、对应的 11.x、12 |
| 添加功能 | 4–10、11、12、15 |
| 架构加固 | 5–10、16、18 |
| 数据或产物维护 | 7、11.6–11.10、12–13 |
| MCP/Agent 体验变化 | 7.6、9.4、11.5/11.11、12 |
| 发布准备 | 12、14–19 |
| 会话交接 | 15、17–20 |

## 2. 文档、代码与决策的关系

### 2.1 永久知识地图

| 资产 | 权威范围 | 维护方式 |
|---|---|---|
| [`AGENTS.md`](../../AGENTS.md) | Agent 必读入口、工作纪律和项目红线 | 保持短而强制；只放全仓库都适用的规则 |
| [通用元指南](../agent-project-continuity-meta-guide.md) | 会话型 Agent 的通用认知、决策和交接协议 | 不写项目具体实现 |
| 本手册 | 当前系统地图、维护方式、演进边界和验证矩阵 | 随语义性维护持续更新 |
| [`docs/rebuild/00`–`07`](../rebuild/00-rebuild-direction.md) | 0.2 V1 已确认的产品、领域、存储、接口和架构决策 | 作为历史决策基线保留，不伪造性回写 |
| [`docs/rebuild/08`](../rebuild/08-implementation-brief.md) | 已完成重构的实施交接和完成定义 | 历史材料，不作为未来阶段计划 |
| [`docs/decisions`](../decisions/README.md) | 重构基线之后的新重大决策与取代关系 | 一项重大决策一份记录 |
| `src/` | 当前运行行为和结构事实 | 不能以“代码已经这样”替代决策正当性 |
| `tests/` 和 CI | 可执行契约与持续证据 | 决策改变时同步更新，不能固化错误意图 |
| README / SECURITY | 用户、Host 和操作者可见承诺 | 用户可见变化必须同步双语材料 |
| CHANGELOG | 待发布与已发布变化、兼容边界及发布相关验证 | 不镜像每个提交，不把源码完成度写成已经发布 |

### 2.2 当前基线与未来决策

`docs/rebuild/00`–`07` 仍然是当前 V1 方向的重要决策依据，但其中的物理文件规划不是永久结构。例如重构后可靠性加固已经把图片 HTTP 生命周期收归 Provider，把本地绝对路径移出 Domain，并拆出了 application view、SQLite row mapping 和 pagination。这些变化保持了原始职责，却使当前代码优于最初的文件级草图。

因此维护时必须区分：

- **长期约束**：产品定位、事实归属、状态语义、隐私与依赖方向；
- **当前机制**：SQLite、具体文件拆分、Pydantic 模型和内部对象形态；
- **历史实施描述**：当时计划的阶段、文件名和验证状态；
- **新事实**：真实 API、SDK、平台或用户需求后来发生的变化。

重大新事实需要改变基线时，在 [`docs/decisions`](../decisions/README.md) 创建新记录，明确取代关系；不要直接改写重构文档，让历史看起来从未改变过。

当前安装与发行方向由 [`0001-use-git-source-distribution.md`](../decisions/0001-use-git-source-distribution.md) 修订：GitHub 源码加 `uvx --from` 是正式用户路径，本地 checkout 是开发路径；PyPI、MCP Registry 和 GitHub Release 暂不属于当前收尾定义。

### 2.3 冲突处理

如果开发者建议、本文、重构文档、代码和测试产生冲突：

1. 判断它们是否只是在描述不同层次的同一事实；
2. 如果确有冲突，停止相关的实质性实现；
3. 查明是代码缺陷、文档过时、测试错误、有意但未记录的偏移，还是新的方向需求；
4. 说明维持与改变各自对产品、数据、契约、安全、运维和兼容性的影响；
5. Agent 给出独立建议，不机械服从开发者，也不机械维护旧文字；
6. 重大变化由有权限的决策者显式确认；
7. 在同一交付中消除决策、文档、代码和测试的静默偏移。

## 3. 十分钟接手路径

### 3.1 必读与现场检查

新 Agent 开始非机械任务时按以下顺序：

1. 阅读根目录 [`AGENTS.md`](../../AGENTS.md)；
2. 完整阅读[通用元指南](../agent-project-continuity-meta-guide.md)和本手册；
3. 执行 `git status --short`、查看当前分支和近期提交，识别用户已有改动；
4. 阅读 README 的“如何工作”“可靠性”“架构”和“开发与验证”部分；
5. 阅读 [`bootstrap.py`](../../src/modelscope_image_gen/bootstrap.py)，恢复运行时装配和资源生命周期；
6. 按任务查阅本手册的代码地图、变更矩阵和对应 `docs/rebuild` 专项文档；
7. 阅读相关端到端路径，而不是只看准备修改的文件；
8. 阅读对应测试，确认现有可执行证据与盲区；
9. 必要时运行当前基线或最小相关测试。

### 3.2 最小项目理解快照

开始实现前，Agent 应能回答：

```text
项目价值：为什么它不是一次普通 HTTP 包装？
主路径：当前需求位于 submit/check/fetch/list/generate 哪一条流程？
事实归属：本地 Job、上游 Task、本地产物和单次操作结果分别代表什么？
规则所有者：该变化属于 Domain、Application、Provider、Repository、Artifact 还是 MCP Adapter？
不变量：哪些可靠性、安全和 Agent 体验不能被破坏？
影响面：是否涉及状态、数据、并发、取消、恢复、wire、日志或发布？
证据：哪些测试和真实环境验证可以证明结果？
```

无法回答这些问题时，不应开始跨边界或高风险修改。

### 3.3 开发基线命令

快速建立环境：

```text
uv sync --locked --all-groups
uv run pytest
```

完整本地门禁：

```text
uv lock --check
uv sync --locked --all-groups
uv run ruff format --check
uv run ruff check
uv run ty check
uv run pytest
uv build --no-sources
```

真实 ModelScope 测试只在明确授权且操作者提供 Token 时运行：

```text
MODELSCOPE_IMAGE_GEN_RUN_LIVE_TESTS=1
MODELSCOPE_SDK_TOKEN=<operator-provided-secret>
uv run pytest -m live tests/live/test_live_modelscope.py
```

该测试会访问外部服务，可能消耗额度。默认测试会因为缺少显式 opt-in 而跳过 live 用例。

## 4. 当前项目身份

### 4.1 一句话定位

ModelScope Image Gen MCP 是一个面向本机或可信工作站中 MCP Agent 的、本地优先、ModelScope 专用、可恢复的文生图任务服务。

核心价值不是发送一次 HTTP 请求，而是维护一组可解释的长期事实：

- 请求是否已经尝试提交；
- 上游是否提供了可靠 Task ID；
- ModelScope 已经明确确认了什么状态；
- 哪些状态仍然不确定；
- 哪些图片已经安全成为本地产物；
- Agent 下一步应 check、fetch，还是停止自动重试；
- 进程重启或会话丢失后如何继续工作。

### 4.2 当前正式能力

固定公开五个工具，顺序也是契约的一部分：

1. `submit_image_generation`
2. `check_image_generation`
3. `fetch_image_generation_result`
4. `list_image_generations`
5. `generate_image`

推荐默认路径：

```text
submit_image_generation
→ 保存本地 Job ID
→ check_image_generation（每次最多一次上游观察）
→ succeeded 后 fetch_image_generation_result
→ 使用本地已验证产物
```

`list_image_generations` 只读取本地摘要，用于找回 Job；`generate_image` 是组合前三个用例的阻塞便利入口，到达本地等待预算后把活动 Job 交还给 Agent。

### 4.3 当前边界

当前 V1 包含：

- 文本生成图片；
- 单一 ModelScope Provider；
- 本地 stdio MCP Server；
- SQLite Job 持久化与恢复；
- 多图片 Job 和部分产物成功；
- Server 管理的本地 Artifact Store；
- 结构化 MCP 输出与面向 Agent 的文本摘要。

当前不以以下能力为目标：

- 图生图、参考图或图片编辑；
- 多 Provider 插件系统；
- 上游任务取消；
- 公网多租户服务；
- HTTP transport、远程文件分发或 OAuth 控制面；
- MCP Resources/Prompts 或 base64 图片传输；
- Web/桌面管理界面；
- 0.1 JSON Job 自动迁移。

这些不是永远禁止，但任何一项都会改变产品、信任或数据边界，属于需要正式决策的变化。

## 5. 系统心智模型

### 5.1 四层事实

维护者必须始终区分：

| 层次 | 事实 | 典型对象 |
|---|---|---|
| 本地任务 | 系统已可靠保存的任务状态 | `GenerationJob` |
| 上游执行 | ModelScope 对外部 Task 的观察结果 | `ProviderTaskReference`、Provider outcome |
| 本地产物 | 单张图片是否已经验证并持久化 | `GeneratedImage`、`LocalArtifact` |
| 单次操作 | 本次 Tool/Use Case 是否成功完成 | Application Result、`ToolOutput.ok` |

最容易造成系统性错误的是把这些事实合并：

- check 网络失败不等于上游 Job 失败；
- 本地等待到期不等于上游 Task timeout；
- 上游 succeeded 不等于所有本地图片 available；
- 成功读取一个 `status=failed` 的终态 Job，仍可以是一次成功的 check 操作；
- fetch 部分成功时，Job 仍然是 succeeded，而产物聚合状态是 partial。

### 5.2 依赖方向

```text
                         bootstrap.py
                 （唯一具体依赖组合根）
                    /                 \
                   v                   v
            mcp_adapter           infrastructure
                   \                   /
                    v                 v
                        application
                            |
                            v
                          domain
```

更精确地说：

- Domain 只表达领域对象、不变量和状态转换；
- Application 依赖 Domain，并定义用例、端口、结果、视图和下一步策略；
- Infrastructure 实现 Application 端口；
- MCP Adapter 消费 Application，用 Pydantic 和 MCP 类型表达 wire；
- Bootstrap 是唯一同时认识具体 Infrastructure 和 MCP Adapter 的位置；
- CLI 只解析命令并进入 bootstrap。

### 5.3 请求经过系统的路径

```text
MCP Call
→ ToolContract 输入 schema 验证
→ ToolHandlers 将 DTO 映射为领域输入
→ Application Use Case 编排
→ Domain 执行状态转换
→ Application Port
→ ModelScope / SQLite / Artifact 具体适配器
→ Application Result 或安全 View
→ MCP mapping 和严格输出 DTO
→ structured content + TextContent
```

Presenter 只能组织已经存在的安全事实；它不能判断业务状态、重试策略或访问基础设施。

### 5.4 Submit

```text
Provider 预验证
→ 创建 UUIDv7 JobId 和 submitting Job
→ SQLite 持久化提交意图
→ 调用 ModelScope
→ accepted：保存 Task ID，转 submitted
→ rejected：保存明确失败
→ unknown：保存 SUBMISSION_OUTCOME_UNKNOWN，禁止自动重提
```

外部请求不得位于 SQLite transaction 内。Token 缺失或 Provider 可在外部调用前确定的输入无效，不创建 Job。

### 5.5 Check

```text
按 JobId 加进程内 keyed lock
→ 读取完整 Job
→ terminal：只返回本地事实
→ active：最多一次 Provider check
→ closed outcome 映射为显式领域转换
→ 临时错误/未知状态：保持原 JobStatus，记录安全操作错误
→ 乐观 revision 保存
```

Provider 成功但返回零图片时，Job 转为 `EMPTY_OUTPUT_IMAGES` 失败；成功返回多图时，一次性创建稳定、连续 position 的图片集合。

### 5.6 Fetch

```text
按 JobId 加 keyed lock
→ 只接受 succeeded Job
→ 跳过 available 图片
→ 对其余图片按上限并发
→ Provider 打开受控图片字节流
→ Artifact Store 限流、校验并原子保存
→ 每张图片使用短且取消屏蔽的 SQLite 更新
→ 返回全部图片的安全 Application View
```

下载或保存失败只改变该图片的 artifact 状态，不推翻上游 succeeded。完整文件已经存在但数据库元数据缺失时，下一次 fetch 会检查文件并修复元数据。

### 5.7 List

List 使用 SQLite 摘要投影和 `(updated_at, job_id)` keyset pagination：

- 不加载完整 `GenerationJob`；
- 不访问 ModelScope；
- 不返回 prompt、negative prompt、Provider locator 或本地产物路径；
- cursor 版本化，并绑定规范化后的 status filter fingerprint；
- 从摘要的状态和计数派生下一步动作。

### 5.8 Generate

Generate 只组合已有 submit、check 和 fetch：

- 不拥有第二套 HTTP、轮询或下载逻辑；
- `max_wait_seconds` 限制本地整次等待预算，包括进行中的 check/fetch；
- 使用 AnyIO cancellation scope；
- 到达预算时返回 `completed=false` 和可继续 check 的 Job；
- 不向上游声明取消，不写入 timeout Job 状态。

### 5.9 启动与关闭

[`build_runtime`](../../src/modelscope_image_gen/bootstrap.py) 当前依次负责：

1. 解析并创建数据目录和 Artifact Root；
2. 创建共享 `httpx.AsyncClient`；
3. 打开 SQLite、设置 PRAGMA、执行 migration；
4. 将残留 `submitting` 恢复为提交结果不确定；
5. 清理过期 `.part` 临时文件；
6. 可选调度终态 Job retention，并处理 cleanup queue；
7. 创建 Provider、Artifact Store、Job locks 和五个用例；
8. 创建 handlers、registry 和低层 MCP Server；
9. 在退出时可靠关闭数据库与 HTTP Client。

配置解析、目录创建、HTTP Client、数据库和 migration 都不得在 package import 阶段发生。

## 6. 当前代码责任地图

| 区域 | 负责 | 明确不负责 | 代表入口 |
|---|---|---|---|
| `domain/` | ID、请求、Job、图片、状态、错误和不变量 | Pydantic、MCP、HTTP、SQLite、文件系统 | [`jobs.py`](../../src/modelscope_image_gen/domain/jobs.py) |
| `application/use_cases/` | 端到端业务编排、端口调用、操作结果 | 具体网络、SQL、MCP wire | [`submit_generation.py`](../../src/modelscope_image_gen/application/use_cases/submit_generation.py) |
| `application/ports/` | Provider、Repository、Artifact、时间、等待和锁的抽象 | 具体第三方类型 | [`provider.py`](../../src/modelscope_image_gen/application/ports/provider.py) |
| `application/provider_outcomes.py` | 封闭的 Provider 观察结果 | 原始 dict、HTTP response | [`provider_outcomes.py`](../../src/modelscope_image_gen/application/provider_outcomes.py) |
| `application/results.py` | 用例结果与内部下一步类型 | MCP Tool 名称 | [`results.py`](../../src/modelscope_image_gen/application/results.py) |
| `application/views.py` | 向适配层暴露的安全、解析后视图 | 持久化 row 或 Provider locator | [`views.py`](../../src/modelscope_image_gen/application/views.py) |
| `application/navigation.py` | 根据应用事实派生 CHECK/FETCH 策略 | MCP 字符串和呈现 | [`navigation.py`](../../src/modelscope_image_gen/application/navigation.py) |
| `infrastructure/modelscope/` | Token 使用、请求、响应验证、状态映射、图片 HTTP 流 | Job 状态转换、文件落盘、SQLite | [`provider.py`](../../src/modelscope_image_gen/infrastructure/modelscope/provider.py) |
| `infrastructure/sqlite/` | migration、事务、revision、row mapping、摘要分页、恢复与清理队列 | Provider 语义、MCP 输出 | [`repository.py`](../../src/modelscope_image_gen/infrastructure/sqlite/repository.py) |
| `infrastructure/artifacts/` | 受控路径、字节/像素/格式验证、哈希、原子提交、文件维护 | URL 下载、更新 Job | [`store.py`](../../src/modelscope_image_gen/infrastructure/artifacts/store.py) |
| `infrastructure/concurrency/` | 同 Job 串行、不同 Job 并发的进程内锁 | 跨进程锁、领域状态 | [`job_locks.py`](../../src/modelscope_image_gen/infrastructure/concurrency/job_locks.py) |
| `infrastructure/config/` | 环境设置、默认路径和 stderr logging | Tool 参数和领域规则 | [`settings.py`](../../src/modelscope_image_gen/infrastructure/config/settings.py) |
| `mcp_adapter/models/` | 严格输入输出 DTO 和 JSON schema | 领域状态转换 | [`inputs.py`](../../src/modelscope_image_gen/mcp_adapter/models/inputs.py) |
| `mcp_adapter/handlers/` | DTO 与应用输入/结果之间的协调 | SQL、HTTP、文件、核心业务策略 | [`tools.py`](../../src/modelscope_image_gen/mcp_adapter/handlers/tools.py) |
| `mcp_adapter/mapping.py` | Domain/Application 到 wire DTO 的显式映射 | 产生新业务事实 | [`mapping.py`](../../src/modelscope_image_gen/mcp_adapter/mapping.py) |
| `mcp_adapter/presenters/` | 从已验证 DTO 生成确定性 TextContent | Provider/Repository 调用和重试判断 | [`common.py`](../../src/modelscope_image_gen/mcp_adapter/presenters/common.py) |
| `mcp_adapter/tool_contract.py` | 输入验证、输出再验证、稳定错误边界、双通道结果 | 具体业务用例 | [`tool_contract.py`](../../src/modelscope_image_gen/mcp_adapter/tool_contract.py) |
| `mcp_adapter/registry.py` | 五个 Tool 的顺序、描述、schema 和 annotations 单一来源 | 动态工具发现或业务实现 | [`registry.py`](../../src/modelscope_image_gen/mcp_adapter/registry.py) |
| `bootstrap.py` | 具体依赖装配和资源生命周期 | 可复用业务规则 | [`bootstrap.py`](../../src/modelscope_image_gen/bootstrap.py) |
| `cli.py` | `--version` 和 stdio 启动入口 | 配置与资源创建 | [`cli.py`](../../src/modelscope_image_gen/cli.py) |

### 6.1 规则归属速查

遇到新规则时先问“谁拥有判断所需的知识”：

- 与 Job/图片合法状态有关：Domain；
- 与多个端口的操作顺序有关：Application Use Case；
- 与下一步 CHECK/FETCH 语义有关：Application navigation；
- 与 ModelScope 请求或原始响应有关：ModelScope Provider；
- 与事务、row、cursor 或 migration 有关：SQLite adapter；
- 与文件字节、真实格式和受控路径有关：Artifact adapter；
- 与 Tool 参数、schema、annotations、文本表达有关：MCP Adapter；
- 与具体实现选择和生命周期有关：Bootstrap。

如果一个判断同时需要两个基础设施的具体知识，通常说明它应该在 Application 通过端口编排，而不是让两个适配器互相调用。

## 7. 不可静默破坏的不变量

以下条目是当前已接受的项目基线。它们可以被新的正式决策取代，但不能在普通缺陷修复、重构或功能实现中顺便改变。

### 7.1 产品与工作流

| ID | 约束 | 为什么存在 | 主要证据 |
|---|---|---|---|
| P1 | **MUST** 维持本地优先、可恢复、面向长任务的产品价值 | 项目不是一次 HTTP 调用包装 | [`00-rebuild-direction.md`](../rebuild/00-rebuild-direction.md)、README |
| P2 | **MUST** 将 submit/check/fetch 作为默认异步路径 | Agent 可以跨调用、跨会话调度任务 | [`registry.py`](../../src/modelscope_image_gen/mcp_adapter/registry.py)、MCP 契约测试 |
| P3 | **MUST** 让 list 只从本地恢复 Job，不批量刷新上游 | 发现任务不能产生隐含网络副作用 | [`list_generations.py`](../../src/modelscope_image_gen/application/use_cases/list_generations.py) |
| P4 | **MUST** 让 generate 复用异步用例 | 避免两套 submit/poll/download 语义漂移 | [`generate_image.py`](../../src/modelscope_image_gen/application/use_cases/generate_image.py) |
| P5 | **CURRENT / REQUIRES DECISION** 固定五个 Tool 及其顺序 | Host、Agent 指引与契约测试依赖该集合 | [`test_tool_contracts.py`](../../tests/mcp_adapter/test_tool_contracts.py) |

### 7.2 任务与错误事实

| ID | 约束 | 为什么存在 | 主要证据 |
|---|---|---|---|
| J1 | **MUST** 以本地 `GenerationJob` 作为系统任务事实来源 | 上游观察和本地恢复需要稳定聚合 | [`jobs.py`](../../src/modelscope_image_gen/domain/jobs.py) |
| J2 | **MUST** 在外部提交前持久化 `submitting` | 崩溃窗口不能让提交意图无痕消失 | [`test_submit_and_check.py`](../../tests/application/test_submit_and_check.py) |
| J3 | **MUST NOT** 自动重试可能已经提交的请求 | 避免重复任务和重复计费 | `SUBMISSION_OUTCOME_UNKNOWN` 领域与应用测试 |
| J4 | **MUST NOT** 把网络错误、解析错误或未知 Provider 状态伪造成 Job 终态 | 不制造不存在的上游事实 | [`check_generation.py`](../../src/modelscope_image_gen/application/use_cases/check_generation.py) |
| J5 | **MUST** 对 terminal Job 的 check 只读取本地事实 | 终态不应被后续网络波动重写 | Check 用例与领域状态机 |
| J6 | **MUST** 保持 JobStatus 为 submitting/submitted/in_progress/succeeded/failed 的显式状态机 | 防止布尔组合和局部隐式转换 | [`states.py`](../../src/modelscope_image_gen/domain/states.py)、领域测试 |
| J7 | **MUST NOT** 将本地等待到期或调用取消写成 Job timeout/canceled | 本地控制流不代表上游事实 | [`test_generate_image.py`](../../tests/application/test_generate_image.py) |
| J8 | **MUST** 区分 Tool 操作成功与 Job 业务成功 | `ok`、`isError` 和 `status` 属于不同事实层 | [`outputs.py`](../../src/modelscope_image_gen/mcp_adapter/models/outputs.py) |
| J9 | **MUST** 只持久化安全 `DomainError`，不保存原始异常或上游正文 | 保持稳定错误语义和隐私边界 | [`errors.py`](../../src/modelscope_image_gen/domain/errors.py)、敏感信息测试 |

### 7.3 多图片与产物

| ID | 约束 | 为什么存在 | 主要证据 |
|---|---|---|---|
| A1 | **MUST** 将一次结果建模为有序多图片集合 | 不假设 Provider 永远只返回一张图片 | `GenerationJob.images`、Provider 多图测试 |
| A2 | **MUST** 保持 image position 从 0 连续且 ImageId 唯一 | 稳定映射数据库、文件和 wire 顺序 | [`jobs.py`](../../src/modelscope_image_gen/domain/jobs.py) |
| A3 | **MUST** 区分上游 succeeded 与每张图片的 pending/available/failed | 下载失败不能推翻生成成功事实 | [`test_generation_job.py`](../../tests/domain/test_generation_job.py) |
| A4 | **MUST** 允许多图部分成功并返回全部当前图片事实 | 一张失败不能丢失其他成功产物 | [`test_fetch_generation_result.py`](../../tests/application/test_fetch_generation_result.py) |
| A5 | **MUST** 跳过 available 图片，不重复下载或覆盖 | fetch 必须可安全重试 | Fetch 应用测试 |
| A6 | **MUST** 在文件原子提交后使用短、取消屏蔽的数据库更新 | 已完成产物不能因兄弟任务取消而丢失 | Fetch cancellation 测试 |
| A7 | **MUST** 能从已存在有效文件修复缺失元数据 | 文件和数据库提交不能成为不可恢复双写 | [`store.py`](../../src/modelscope_image_gen/infrastructure/artifacts/store.py) |
| A8 | **MUST** 以真实图片内容决定格式、媒体类型和扩展名 | 不信任 URL 或 Content-Type | Artifact Store 测试 |
| A9 | **MUST NOT** 让 Agent 指定最终目录、文件名或绝对路径 | 文件系统是安全边界 | MCP schema 与 Artifact path 测试 |
| A10 | **MUST** 保持正式产物在受控 Artifact Root 内并原子提交 | 防止路径逃逸、半文件和覆盖 | [`LocalArtifactStore`](../../src/modelscope_image_gen/infrastructure/artifacts/store.py) |

### 7.4 数据、恢复与并发

| ID | 约束 | 为什么存在 | 主要证据 |
|---|---|---|---|
| D1 | **MUST** 使用显式 schema version 和只向前 migration | 已发布本地数据不能依赖代码猜测结构 | migration SQL、Repository open |
| D2 | **MUST** 使用 revision 乐观并发检测 | 防止较旧聚合静默覆盖新事实 | [`test_sqlite_repository.py`](../../tests/infrastructure/test_sqlite_repository.py) |
| D3 | **MUST NOT** 在 SQLite write transaction 内执行网络、等待或 Pillow 工作 | 避免长锁、取消和恢复问题 | Repository 与用例边界 |
| D4 | **MUST** 让同 Job check/fetch 在进程内串行，不同 Job 可以并发 | 保持聚合更新顺序而不全局串行 | [`job_locks.py`](../../src/modelscope_image_gen/infrastructure/concurrency/job_locks.py) |
| D5 | **MUST** 在启动时安全收束残留 `submitting` | 没有可靠 Task ID 时只能表达不确定 | recovery 测试 |
| D6 | **MUST** 让 list 使用摘要投影而非完整聚合 | 隐私最小化并避免无谓加载敏感字段 | [`row_to_summary`](../../src/modelscope_image_gen/infrastructure/sqlite/row_mapping.py) |
| D7 | **MUST** 让 cursor 不透明、版本化并绑定筛选条件 | 防止错误分页和跨筛选复用 | [`pagination.py`](../../src/modelscope_image_gen/infrastructure/sqlite/pagination.py) |
| D8 | **MUST NOT** 由 retention 删除活动 Job；数据库和文件删除通过 cleanup queue 协调 | 避免活动事实丢失和不可恢复半删除 | Repository maintenance、配置存储契约 |

### 7.5 架构与生命周期

| ID | 约束 | 为什么存在 | 主要证据 |
|---|---|---|---|
| L1 | **MUST** 保持 Domain 无框架依赖 | 领域事实不由传输或存储塑形 | [`test_architecture.py`](../../tests/test_architecture.py) |
| L2 | **MUST** 保持 Application 不依赖 Infrastructure/MCP，且不用 `Any` 贯穿核心边界 | 端口可替换、类型语义清晰 | Architecture test |
| L3 | **MUST** 保持 MCP Adapter 不依赖具体 Infrastructure | Tool 只是输入输出适配 | Architecture test |
| L4 | **MUST** 让 Provider 拥有 HTTP response 和图片流生命周期 | 网络错误在 Provider 边界净化 | Provider download 测试 |
| L5 | **MUST** 让 Artifact Store 保持 Provider-neutral，不导入 HTTPX | 文件安全不依赖 URL 或 HTTP | Architecture test |
| L6 | **MUST** 让 Bootstrap 成为唯一 composition root | 避免具体依赖散落和隐式全局状态 | [`bootstrap.py`](../../src/modelscope_image_gen/bootstrap.py) |
| L7 | **MUST** 保持 import 无 Settings、目录、数据库、HTTP 或 migration 副作用 | package 元数据和 CLI 可安全读取 | [`test_cli.py`](../../tests/test_cli.py) |
| L8 | **MUST** 在取消和启动失败时关闭或回滚已获得资源 | stdio 长生命周期不能泄漏连接或锁 | Bootstrap、Repository cancellation 路径 |
| L9 | **MUST NOT** 从新代码导入 `legacy` | 归档不是兼容层或共享库 | Architecture test |

### 7.6 MCP 与 Agent 体验

| ID | 约束 | 为什么存在 | 主要证据 |
|---|---|---|---|
| M1 | **MUST** 由 Pydantic 模型生成并再次验证输入/输出 schema | wire 不能依赖手写漂移 | [`tool_contract.py`](../../src/modelscope_image_gen/mcp_adapter/tool_contract.py) |
| M2 | **MUST** 使用严格 `ok/data/error` envelope | 自动化消费者需要稳定形状 | Tool envelope 测试 |
| M3 | **MUST** 让 `isError == not ok` | MCP 协议结果与结构化操作事实一致 | ToolContract |
| M4 | **MUST** 同时返回 structured content 和简洁 TextContent，并保持语义一致 | 机器解析和 Agent 阅读各有稳定入口 | Presenter 与内存 Client 测试 |
| M5 | **MUST** 从 Application 事实派生 next action | 下一步策略不能散落在 presenter | [`navigation.py`](../../src/modelscope_image_gen/application/navigation.py) |
| M6 | **MUST** 在 Tool description/annotations 中如实表达外部访问、副作用、幂等性和推荐路径 | Agent 在调用前需要审批与调度信息 | [`registry.py`](../../src/modelscope_image_gen/mcp_adapter/registry.py) |
| M7 | **MUST** 把已知工具的验证和应用错误表达为 Tool result；未知工具使用协议错误 | 保持 MCP 边界稳定 | Server 与 ToolContract tests |
| M8 | **MUST** 让 list 在没有 Token 时可用；缺 Token 不阻止 Server 启动 | 本地恢复能力不能依赖上游凭据 | MCP contract tests |

### 7.7 安全与隐私

| ID | 约束 | 为什么存在 | 主要证据 |
|---|---|---|---|
| S1 | **MUST NOT** 持久化或返回 Token、Authorization Header | 秘密不属于 Job 事实 | Sensitive data tests |
| S2 | **MUST NOT** 在默认日志记录 prompt、Provider locator、原始上游正文或产物绝对路径 | 本地日志也可能被收集和备份 | [`test_sensitive_data.py`](../../tests/infrastructure/test_sensitive_data.py) |
| S3 | **MUST** 抑制 HTTPX 默认完整 URL 日志 | Task path 和签名 locator 可能敏感 | [`logging.py`](../../src/modelscope_image_gen/infrastructure/config/logging.py) |
| S4 | **MUST** 把数据库、WAL/SHM、生成图片和备份视为敏感本地数据 | 它们包含 prompt、locator 和用户产物 | README / SECURITY |
| S5 | **MUST** 验证 UUID、相对路径、SHA-256、symlink 和 Windows junction/reparse point | 防止路径伪造与 root 逃逸 | Domain/Artifact tests |
| S6 | **MUST** 让 stdout 只承载 MCP wire，日志只写 stderr | stdio 协议不能被诊断文本污染 | Logging/stdio 设计 |

## 8. 当前机制、允许演进与决策门槛

### 8.1 可以在现有边界内自主完成

在保持第 7 章不变量且完成相称验证时，Agent 通常可以自主：

- 重命名或拆分私有模块，使职责更清晰；
- 提取小型、单一职责策略对象；
- 增加索引、查询投影或窄性能优化，不改变数据语义；
- 改善内部错误映射和安全消息，不改变公开 reason code 含义；
- 强化输入、上游响应、图片或路径验证；
- 增加证明既有契约的测试；
- 改善取消、关闭、回滚和临时文件清理；
- 在不改变 wire 和领域语义的情况下调整 presenter 文案；
- 修正当前实现与已接受决策之间的明确偏差。

“可以自主”不等于不需要全局检查。跨层影响、用户可见变化和新测试仍要在交付中说明。

### 8.2 通常需要影响分析，但不一定需要 ADR

- 增加现有文生图请求的可选参数；
- 支持 ModelScope 已证实的新 pending/running 状态别名；
- 新增不改变状态机的稳定错误码；
- 增加受控图片格式；
- 新增配置项或安全上限；
- 调整默认超时、等待或并发值；
- 优化 SQLite 查询或 Artifact 检查流程；
- 改变用户可见 TextContent，但不改变结构化事实。

如果这些变化会破坏兼容性、改变数据语义、安全边界或外部副作用，则升级为正式决策。

### 8.3 必须先形成正式决策

- 增删、重命名或重新排序公开 Tool；
- 改变 Tool input/output schema 的兼容边界；
- 增删 JobStatus、ArtifactStatus，或改变现有状态含义；
- 改变 `ok`、`isError`、部分成功或 next action 语义；
- 自动重试 submit、引入上游取消或把本地超时写入 Job；
- 新增 Provider、多 Provider 插件机制、图生图或编辑；
- 改变 SQLite 为其他存储、引入跨进程/多节点写入；
- 允许 Agent 控制路径、返回 base64/MCP Resource 或远程分发文件；
- 改变 stdio/本地可信工作站的部署与信任模型；
- 引入 HTTP transport、认证、多租户或远程控制面；
- 更换 Python、AnyIO、MCP SDK 大版本、构建后端或质量工具；
- 为旧数据建立迁移，或改变正式数据保留/删除承诺；
- 弱化敏感信息、路径、字节、像素或格式安全边界。

决策记录写入 [`docs/decisions`](../decisions/README.md)，必须说明旧约束、方案、迁移、验证和重新评估条件。

## 9. 当前代码风格与设计语言

代码风格不只是 Ruff 格式。未来代码应该延续当前项目表达领域、边界和副作用的方式；如果现有模式不足，应显式改善，而不是静默引入第二种风格。

### 9.1 Domain

- 使用 `from __future__ import annotations`；
- 使用 `@dataclass(frozen=True, slots=True)` 表达不可变值和聚合；
- 使用 `StrEnum` 表达稳定封闭状态；
- 在 `__post_init__` 中维护构造不变量并规范化输入；
- 使用 `dataclasses.replace` 产生新状态，不原地修改；
- 状态转换由 `GenerationJob`/`GeneratedImage` 方法拥有，不由 handler 或 row mapper 拼装；
- 有序集合使用 tuple，position 和 ID 不变量由聚合验证；
- DomainError 只包含稳定、安全、可持久化的字段；
- 不导入 Pydantic、MCP、HTTPX、aiosqlite、Pillow 或 platformdirs。

代表性实现：[`GenerationJob`](../../src/modelscope_image_gen/domain/jobs.py)、[`GeneratedImage`](../../src/modelscope_image_gen/domain/artifacts.py)。

### 9.2 Application

- 用一个明确的 Use Case class 表达一项应用能力，并通过 `__call__` 执行；
- 构造函数只接收端口、策略和系统能力，不读取全局配置；
- Provider 原始响应先映射为封闭 outcome union，再进入用例；
- 用例负责操作顺序和跨端口协调，Domain 负责状态合法性；
- Application Result 表达单次操作事实，View 表达对外安全读取；
- next step 使用内部 `NextStepKind`，MCP Tool 名称由 Adapter 再映射；
- 不使用 `Any` 连接 Domain、Application 和 Infrastructure；
- 对封闭 union 显式穷举，并对不可能类型抛出 `TypeError`，避免静默 fallback。

代表性实现：[`SubmitGeneration`](../../src/modelscope_image_gen/application/use_cases/submit_generation.py)、[`FetchGenerationResult`](../../src/modelscope_image_gen/application/use_cases/fetch_generation_result.py)。

### 9.3 Infrastructure

- 适配器只解释自己拥有的外部细节，并在边界净化错误；
- Provider 可以使用 HTTPX 类型，但端口不能泄露这些类型；
- Repository 使用显式 SQL、row mapping 和 transaction，不把 row 当领域对象；
- Artifact Store 只接收受控 ID 和字节流，不接收 URL、原始 MCP 路径或 Repository；
- 配置只在启动边界解析，通过构造注入；
- 时间使用 UTC，持久化和 wire 使用 ISO 8601；
- 捕获异常时保持范围窄，保留取消语义，不把所有错误吞成通用失败；
- 外部请求、Pillow 检查和长等待不放在数据库事务中。

### 9.4 MCP Adapter

- Input/Output DTO 使用 Pydantic，`extra="forbid"`；
- DTO 不充当领域对象，handler 必须显式映射；
- `ToolContract` 同时拥有 schema 生成、执行验证和稳定错误边界；
- Registry 是 Tool 名称、顺序、title、description 和 annotations 的单一来源；
- Mapping 只转换事实，不重新判断业务；
- Presenter 只消费已经验证的安全 DTO，保持输出短、确定、可行动；
- 不把完整 JSON 镜像到 TextContent；
- 不为旧接口增加隐藏 alias，除非正式兼容决策要求。

### 9.5 错误风格

新增错误必须回答：

```text
code：Agent 能稳定识别的原因是什么？
stage：在哪个操作阶段发生？
category：属于验证、配置、网络、上游、存储还是状态冲突？
retryable：重试同一操作是否可能安全成功？
retry_after_seconds：是否有可靠等待建议？
possibly_submitted：是否存在重复提交风险？
provider_request_id：是否有安全且有用的诊断 ID？
safe_message：不依赖内部异常也能指导 Agent 的英文消息是什么？
```

不要根据异常类名临时生成公开 code；不要把 traceback、URL、Token、原始 body 或本地内部路径放进安全消息。

### 9.6 异步、取消与并发风格

- 使用 AnyIO 作为异步和取消抽象，不混入另一套调度框架；
- 资源生命周期使用 async context manager / `AsyncExitStack`；
- 同 Job 的聚合写操作通过 keyed lock 串行；
- 图片并发使用 `CapacityLimiter`，并发上限来自 Server 配置；
- 只对必须完成的短原子后半段使用 cancel shield；
- `BaseException` 只在资源清理和 transaction 回滚边界谨慎捕获并重新抛出；
- 不把取消转成普通 DomainError，除非未来正式定义新的外部语义。

### 9.7 日志风格

- 使用稳定事件名和 `key=value` 字段；
- 日志服务于本地诊断，不参与业务控制流；
- Job/Image 使用受控 ID 关联；
- 不记录 prompt、negative prompt、Token、Authorization、Provider locator、原始 body 或产物绝对路径；
- 日志只写 stderr；
- 新 HTTP 客户端或库必须检查其默认日志是否暴露 URL 或 header。

### 9.8 模块与命名

- 名称优先表达职责和领域含义，不使用模糊缩写；
- 不建立无明确边界的 `utils.py`、`helpers.py` 或全能 `service.py`；
- 一个模块明显超过约 300 行时检查职责，但不为满足行数机械拆分；
- 小型策略可以作为明确私有 helper；跨边界规则必须有正式所有者；
- 新抽象应消除真实重复或表达稳定概念，不为猜测中的未来需求提前设计插件体系；
- 代码注释解释不明显的原因、竞态或安全约束，不重复代码表面动作。

### 9.9 测试风格

- Domain 测试纯标准库，不触碰网络、SQLite 或正式文件目录；
- Application 测试使用小型内存端口和可控 Clock/ID/Waiter；
- Provider 测试使用 HTTPX MockTransport 和脱敏响应；
- SQLite 测试使用临时数据库，覆盖 migration、round-trip、revision 和 restart；
- Artifact 测试使用临时 root 与真实图片字节，覆盖安全失败；
- MCP 测试使用 Registry/ToolContract 和官方内存 Client；
- live 测试必须显式 opt-in，默认 skip；
- 测试名表达被保护的不变量，而不只描述函数调用；
- 修复根因时增加能阻止同类回归的测试，不只锁定当前样例。

## 10. 项目级全局维护流程

### 10.1 接管与基线

1. 保护工作区已有改动；
2. 根据第 3 章恢复项目心智模型；
3. 阅读相关 `docs/rebuild`、近期变更和测试；
4. 必要时运行当前失败复现或最小基线；
5. 明确哪些结论来自真实运行、测试、文档或推断。

### 10.2 形成变更命题

```text
目标：改善哪个 Agent/Host/操作者结果？
根因：问题发生在哪个事实或边界？
必须保持：第 7 章哪些不变量相关？
非目标：哪些邻近能力本次不扩张？
成功证据：哪个层次能够证明修复，是否需要 live/Host？
```

### 10.3 项目影响扫描

按风险检查：

```text
产品定位与五工具工作流
→ GenerationRequest / GenerationJob / GeneratedImage / DomainError
→ submit/check/fetch/list/generate 应用语义
→ Provider outcome 和上游契约
→ SQLite schema、revision、恢复、分页与 retention
→ Artifact 下载、验证、路径、原子提交与修复
→ 并发、取消、等待预算与资源关闭
→ MCP input/output、ok/isError、next action、description 和 TextContent
→ Token、prompt、locator、日志、路径和构建产物隐私
→ 单元、集成、契约、stdio、wheel、Host 和 live 证据
→ README、SECURITY、CHANGELOG、决策和本手册
```

不是每项都要修改，但高风险变更应能说明为什么某项不受影响。

### 10.4 根因与最小完整改动

在编码前确认：

- 相同能力是否还有其他入口；
- 规则是否已经在另一个层实现；
- 最近函数里的 `if` 是否会产生新例外；
- 是否应该扩展领域不变量、应用策略或适配器映射；
- 是否会创建第二套 submit/check/fetch 或错误/状态解释；
- 取消、失败、恢复和部分成功是否仍然成立；
- 修改后新 Agent 能否从结构理解，而不依赖本次会话解释。

### 10.5 独立建议与决策

发现开发者建议与项目全局冲突时，Agent 必须：

1. 先复述目标；
2. 指出具体冲突和证据；
3. 说明遗漏的全局影响；
4. 给出替代方案和推荐；
5. 区分事实、推断和偏好；
6. 对第 8.3 节变化请求显式决策。

决策者知情确认后，Agent 应贯彻决定并更新永久知识；除非出现新的重大证据，不要在执行阶段继续重复同一争论。

### 10.6 纵向实施与验证

- 先写或确认能够失败的证据；
- 在真正拥有规则的层修改；
- 必要时穿过完整纵向路径，不用 adapter 临时绕过；
- 从针对性测试开始，再运行相称的全局门禁；
- 完成后回看变更命题和第 7 章，不以“测试绿了”替代全局复核；
- 把未运行的真实环境证据清楚留在交付中。

### 10.7 永久知识回写

根据变化同步：

- 重大方向：`docs/decisions`；
- 当前系统和维护方式：本手册；
- Agent 强制入口：`AGENTS.md`；
- 用户/Host 行为：双语 README；
- 安全报告与数据边界：SECURITY；
- 待发布与已发布的用户可见变化：CHANGELOG；
- 可执行约束：测试和 CI；
- 历史重构材料：只建立取代关系，不回写历史。

## 11. 常见变更影响矩阵

先使用下表定位完整路径，再阅读后续配方。表中的“通常涉及”不是要求无条件修改全部文件，而是提醒维护者逐项确认。

| 变更类型 | 通常涉及 | 关键风险 | 最低证据 |
|---|---|---|---|
| 新增生成参数 | MCP input → handler → `GenerationRequest` → Provider validate/payload → SQLite | 默认值、规范化、持久化、Provider 兼容 | DTO、应用/Provider、round-trip 测试 |
| 新 Provider 状态 | Provider mapping → closed outcome → Check → Domain transition | 未知状态被伪造成终态 | MockTransport + 状态保持测试 |
| 新错误码 | `ErrorCode` → 产生边界 → Application/MCP mapping → presenter | retry/提交不确定语义错误、泄密 | 错误契约 + sensitive-data 测试 |
| Job/Artifact 状态变化 | Domain → schema/migration → row mapping → list/navigation → MCP DTO/text | 旧数据、状态组合、Agent 控制流 | ADR + migration + 全纵向测试 |
| Tool schema 或工具集合 | DTO → handler → result/mapping → registry/server/presenter | Host 兼容、副作用与 `isError` | ADR + schema + Client + Host |
| SQLite 变化 | 新 migration → version runner → mapping/repository → package data | 老库升级、回滚、数据丢失 | v1→新版本迁移 + restart + wheel |
| Artifact 策略 | port/use case → Store → metadata/view/wire | 路径逃逸、损坏、双写、取消 | 真实图片 + 攻击路径 + cancellation |
| 配置项 | Settings → bootstrap/adapter → `.env.example`/README | Tool 越权、安全默认值、启动失败 | 配置测试 + 相关集成测试 |
| 并发/取消 | use case → lock/transaction/resource lifecycle | 丢事实、死锁、半提交 | 可控调度的 deterministic 测试 |
| List 查询 | query/view → pagination/repository → mapping/DTO | 敏感字段泄漏、cursor 错页 | privacy + cursor/filter 测试 |
| Text/日志 | application facts → mapping/presenter/log boundary | 语义冲突、敏感信息 | contract + sentinel capture |
| 新 Provider/编辑/远程能力 | 产品、领域、数据、Artifact、MCP、信任模型 | 整体方向变化 | Accepted ADR + 分阶段验证 |

### 11.1 添加文生图请求参数

1. 先判断它是领域请求事实、ModelScope 特有选项，还是服务器工作流控制：
   - 会随 Job 恢复并决定生成内容的参数通常属于 `GenerationRequest`；
   - 轮询、并发、路径和安全上限属于服务器配置，不应伪装成生成请求；
   - 仅用于 `generate` 本地等待的参数属于该 Tool/Application 调用，不进入 Job。
2. 在 [`inputs.py`](../../src/modelscope_image_gen/mcp_adapter/models/inputs.py) 定义 wire 类型、默认、范围和规范化。
3. 在 [`ToolHandlers._request`](../../src/modelscope_image_gen/mcp_adapter/handlers/tools.py) 显式映射，不把 Pydantic DTO 传入 Domain。
4. 如果是稳定请求事实，扩展 [`GenerationRequest`](../../src/modelscope_image_gen/domain/requests.py) 及其不变量。
5. 在 ModelScope Provider 中做 Provider-specific 验证并构建 payload；不能由 raw dict 穿过 Application。
6. 由于完整请求需要跨重启恢复，检查 SQLite schema、row mapping 和 migration。
7. 判断 Job/List/Tool output 是否应公开该字段；隐私最小化的 list 默认不应增加 prompt 类信息。
8. 更新输入 schema、Provider payload、Repository round-trip、README 和必要的 live 证据。

不要把参数只加到 Tool schema 和 HTTP payload 而不考虑恢复；也不要把 ModelScope 当前模型的偶然范围全部升级为通用 Domain 不变量。

### 11.2 适配新的 ModelScope 状态或响应字段

1. 取得真实官方文档或脱敏响应证据；不要根据名字猜测终态含义。
2. 在 [`ModelScopeProvider`](../../src/modelscope_image_gen/infrastructure/modelscope/provider.py) 验证原始 JSON 形状。
3. 如果新状态等价于现有 pending/running/succeeded/failed，只映射到现有 closed outcome，不增加 JobStatus。
4. 如果语义未知，继续返回 `ProviderUnknownStatus`，保持本地 JobStatus。
5. 只有新事实无法由现有状态表达时，才启动状态机正式决策。
6. 增加 MockTransport fixture，覆盖缺字段、错误类型、空多图、未知值、request ID 和 Retry-After。
7. 发布候选若依赖新上游行为，运行显式 live 样本并如实记录。

### 11.3 新增或修改 ErrorCode

1. 先判断错误属于领域稳定原因，还是只应留在日志中的内部诊断。
2. 在 [`errors.py`](../../src/modelscope_image_gen/domain/errors.py) 添加稳定 code，并定义 stage/category/retryable。
3. 在最早拥有事实的边界创建净化后的 `DomainError`：输入、Provider、Repository、Artifact 或 ToolContract。
4. 检查该错误是否保持 Job 状态、使 Job 终态、只使单图失败，或只使本次操作失败。
5. `possibly_submitted=true` 仍然只允许 `SUBMISSION_OUTCOME_UNKNOWN`。
6. 检查 next action、TextContent、list summary 和日志行为。
7. 用唯一哨兵验证原始异常、Token、URL/body 不进入数据库、structured content、TextContent 和 stderr。

错误 code 是公开 Agent 契约。重命名、合并或改变 retry 语义通常需要正式兼容决策。

### 11.4 修改 JobStatus 或 ArtifactStatus

这是高风险变化，必须先有 Accepted 决策。完整影响至少包括：

```text
Domain enum 和聚合构造/转换不变量
→ Application check/fetch/generate/navigation
→ Provider outcome 或 Artifact 失败语义
→ SQLite CHECK constraint、新 migration 和 row mapping
→ List 聚合投影、filter、cursor fingerprint
→ MCP input enum、output DTO、next action 和 presenter
→ README 状态说明、恢复手册和 CHANGELOG
→ 旧数据库升级、所有非法组合和端到端测试
```

不得只向 enum 添加成员；数据库约束、穷举分支和 Agent 下一步动作会因此失配。

### 11.5 修改 Tool 或 wire contract

1. 先判断是否兼容：新增可选字段、改变默认值、收紧校验、重命名字段的风险不同。
2. 更新对应 Input/Output Pydantic 模型，不手写平行 JSON schema。
3. 更新 Application Result/View（如果事实层确实变化）、handler 和 mapping。
4. 在 Registry 同一位置维护 name、顺序、description 和 annotations。
5. 检查 `ok/data/error`、`isError`、TextContent 和 next action 一致性。
6. 更新 server instructions、双语 README 和 `docs/rebuild` 的取代决策关系。
7. 运行 ToolContract、官方内存 Client、真实 stdio；重要兼容变化需要真实 Host。

新增 Tool、删除 Tool、重命名或重新排序必须先写 ADR。不要用隐藏 alias 暂时规避正式兼容决策。

### 11.6 添加 SQLite migration

`v001_initial.sql` 已随发布基线存在，**不得修改它来伪装新库结构**。正确路径是：

1. 写新的、递增版本 migration；
2. 将 `SCHEMA_VERSION` 提升到新版本；
3. 扩展 Repository open，使它从当前 `user_version` 逐步、事务性迁移到目标版本；
4. 明确每一步失败后的数据库状态和重试方式；
5. 更新 SQL constraint、row mapping、query 和领域 round-trip；
6. 使用真实 v1 schema/fixture 创建旧库，再打开并验证升级；
7. 验证新库初始化和旧库升级两条路径；
8. 验证 schema 更新后重启、revision、foreign key、WAL 和分页；
9. 构建 wheel，确认所有 migration SQL 都作为 package data 存在；
10. 在用户可见时记录备份、不可逆变化和兼容边界。

当前实现拒绝比代码更新的 schema version。不要用自动降级或忽略未知列来掩盖版本不匹配。

### 11.7 修改 Artifact Store 或增加图片格式

1. 保持 Provider 打开网络流、Artifact Store 消费字节流的边界。
2. 扩展格式时同时维护真实格式、受控扩展名和媒体类型映射。
3. 验证 Content-Length 只能作为提前拒绝提示，实际流字节仍必须计数。
4. 使用 Pillow 验证真实格式、宽高、像素和完整图片；保存原始字节，不重新编码。
5. 最终路径只能由 JobId、ImageId、position 和验证后格式派生。
6. 检查 symlink、junction/reparse point、混合分隔符、绝对路径、`..` 和 path-swap。
7. 原子提交前再次验证路径；失败时尽力清理 `.part`。
8. `inspect_existing` 必须受同样的字节、格式、像素和路径约束。
9. 运行损坏文件恢复、元数据修复、重复 fetch、取消和多图片部分成功测试。

### 11.8 新增配置项

1. 决定它是秘密、路径、安全上限、网络参数、工作流默认值还是保留策略。
2. 使用 `MODELSCOPE_IMAGE_GEN_` 前缀；ModelScope Token 继续使用生态名称 `MODELSCOPE_SDK_TOKEN`。
3. 在 `Settings` 中定义类型、默认值和启动验证；秘密使用 `SecretStr`。
4. 通过 Bootstrap 注入需要它的具体对象，不让 Domain 或 Tool 直接读取环境变量。
5. 安全上限不能被 Tool 参数放宽。
6. 更新 `.env.example` 和双语 README 配置表。
7. 检查 Token 缺失是否仍允许 Server 启动和本地 list/终态读取。
8. 修改默认行为时评估兼容性，并更新测试与 CHANGELOG。

### 11.9 修改并发、取消或等待

1. 画出取消发生在网络前、网络中、原子文件提交后、数据库 transaction 中和多图兄弟任务中的行为。
2. 保持同 Job 串行，不把所有 Job 全局锁住。
3. 保持 revision 作为数据库最后防线；进程内 lock 不能替代乐观并发。
4. cancel shield 只包围必须完成的短提交/回滚，不屏蔽整个网络或图片处理。
5. generate 等待预算覆盖 check/fetch，不只覆盖 sleep。
6. 测试使用可控 Clock/Waiter/Event，不依赖脆弱的真实 sleep 竞态。
7. 明确区分本地取消和上游取消；当前没有上游取消能力。

### 11.10 修改 List、分页或摘要

- 保持 list 完全本地、只读、不触发 Provider；
- 使用 SQL summary projection，不为列表批量重建完整 Job；
- 不返回 prompt、negative prompt、Provider locator 或产物路径；
- 排序字段和 cursor payload 必须一起演进并版本化；
- filter 规范化必须与 fingerprint 一致；
- 新摘要字段需要评估是否会泄露敏感或大字段；
- next action 继续由 Application navigation 从摘要事实派生。

### 11.11 修改日志或 TextContent

- 日志变化先检查敏感字段，不把“便于诊断”作为泄密理由；
- TextContent 从已验证 structured DTO 派生，不独立查询或判断；
- Agent 每次结果应能看懂操作结果、Job 状态、产物与下一步；
- 提交结果不确定必须明确禁止自动重提；
- fetch/generate 返回 available 文件列表；list 保持紧凑；
- 修改 presenter 时同时运行成功、失败、partial、等待预算到期和空列表契约测试。

### 11.12 新 Provider、图生图、编辑或远程能力

这些变化不能被当作“再加几个参数”。开始编码前必须回答：

- 产品仍是 ModelScope 专用还是变为多 Provider？
- `GenerationRequest`、Job、图片与输入产物的领域模型如何变化？
- Provider Task 和本地 Job 的事实关系是否仍成立？
- 输入图片如何传输、验证、持久化和清理？
- 本地 stdio 路径可见性是否仍成立？
- wire、数据迁移、认证、隐私与配额副作用如何表达？
- 现有五工具是扩展、替换还是保留？
- 老 Job 和 Host 如何兼容？

必须先形成产品与架构决策，再分纵向切片实施，不要把现有文本生成路径逐步堆成条件分支中心。

## 12. 验证体系

### 12.1 当前自动化基线

在页首复核基线，源码包含 40 个测试：39 个默认自动化测试和 1 个显式 live 测试。数量只是新鲜度线索，不是质量目标；未来增加或重组测试时应更新相关说明，不应为了维持数字限制测试演进。

| 层次 | 当前主要保护内容 | 入口 |
|---|---|---|
| Domain | 状态机、多图片、等待非状态、Artifact 不变量与安全相对路径 | [`tests/domain`](../../tests/domain) |
| Application | 提交时序、不确定提交、单次 check、多图、partial、幂等 fetch、取消与等待预算 | [`tests/application`](../../tests/application) |
| Provider | submit/check/download 映射、未知状态、畸形响应、seed、HTTP 错误 | [`test_modelscope_provider.py`](../../tests/infrastructure/test_modelscope_provider.py) |
| SQLite | round-trip、revision、恢复、摘要和 cursor | [`tests/infrastructure`](../../tests/infrastructure) |
| Artifact | 真实图片验证、安全落盘、路径边界 | [`test_artifact_store.py`](../../tests/infrastructure/test_artifact_store.py) |
| Privacy | Token/body/URL/prompt 日志边界 | [`test_sensitive_data.py`](../../tests/infrastructure/test_sensitive_data.py) |
| Architecture | 跨层导入、legacy、Artifact/HTTP 边界 | [`test_architecture.py`](../../tests/test_architecture.py) |
| MCP contract | 五工具顺序、schema、envelope、Token-free list、稳定 reason code | [`tests/mcp_adapter`](../../tests/mcp_adapter) |
| CLI/config | import 无副作用、`--version`、`.env.local` 与默认模型 | [`test_cli.py`](../../tests/test_cli.py) |
| Live | 真实 submit/check/fetch 和本地产物 | [`test_live_modelscope.py`](../../tests/live/test_live_modelscope.py) |

### 12.2 按变化选择门禁

| 变化 | 必须运行 |
|---|---|
| Domain/状态 | 对应 domain + application + architecture + 全 pytest |
| Use Case | 对应 application + MCP contract + 全 pytest |
| Provider | MockTransport、sensitive data、全 pytest；发布候选按需 live |
| SQLite | migration/round-trip/restart/revision/pagination + 全 pytest + build/wheel |
| Artifact | 真实图片、路径攻击、partial/cancellation + Windows/Ubuntu |
| MCP | ToolContract、官方内存 Client、stdio；重要变化真实 Host |
| Config/CLI/logging | CLI、sensitive data、stdio stdout/stderr 分离 |
| Package data/build | lock、build、wheel 内容、隔离安装和 console script |
| 用户可见行为 | 双语 README、CHANGELOG、对应端到端证据 |

### 12.3 完整质量门禁

```text
uv lock --check
uv sync --locked --all-groups
uv run ruff format --check
uv run ruff check
uv run ty check
uv run pytest
uv build --no-sources
```

CI 当前在 Windows 和 Ubuntu 上运行同步、格式、Lint、类型、测试、构建和隔离 wheel console-script smoke test。CI 配置存在不等于对应平台最近一次已经真实通过；发布报告应引用实际 run，而不是配置意图。

### 12.4 证据等级必须分开报告

从低到高不要混淆：

```text
代码阅读与推断
→ 纯单元测试
→ MockTransport / 临时 SQLite / 临时文件集成测试
→ 官方 MCP 内存 Client
→ 真实 stdio 子进程
→ 从 wheel 隔离安装后的入口
→ 从远端 Git 通过 uvx 构建并运行入口
→ 真实 MCP Host
→ 真实 ModelScope API 与产物
→ 可选发行渠道的实际发布
```

MockTransport 通过不能写成真实 API 已验证；本地源码运行不能替代远端 Git 安装或 wheel；未来的 Registry 配置完成也不能写成已经发布。未运行项是交付事实，不是可以省略的尴尬信息。

### 12.5 Live 测试纪律

- 必须同时存在显式 flag 和 Token；
- 没有条件时 skip，不失败，也不产生网络；
- prompt 不包含个人信息或秘密；
- 产物写入临时测试目录；
- 运行前说明可能消耗外部额度；
- 失败时保存安全的 request ID 和阶段，不保存签名 URL、Token 或完整响应；
- 改变 Provider 控制流时，真实证据应标明模型、尺寸、日期和实际路径，不把一次样本泛化为所有模型保证。

## 13. 运行数据与维护

### 13.1 数据布局

默认由 platformdirs 选择用户数据目录：

```text
<data_dir>/
├── state.sqlite3
├── state.sqlite3-wal      # 运行时可能存在
├── state.sqlite3-shm      # 运行时可能存在
└── artifacts/
    └── jobs/
        └── <job_id>/
            ├── .tmp/*.part
            └── <position>-<image_id>.<verified-extension>
```

正式数据不在包目录、源码目录或 `uvx` 临时环境中。数据库保存 prompt、negative prompt、Provider Task/locator、安全错误和 Artifact 元数据；图片保存用户生成内容。数据库、WAL/SHM、Artifact、备份和诊断副本都应视为敏感数据。

### 13.2 备份与恢复

- 最安全的文件级备份是在 Server 停止、SQLite 已关闭后，同时备份数据库和 Artifact Root；
- Server 活动时不要只复制主 `.sqlite3` 而忽略 WAL/SHM；需要在线备份时应实现或使用 SQLite 一致性备份机制；
- 数据库与 Artifact 应作为同一逻辑数据集保留，避免元数据与文件时间点相差过大；
- 恢复前确认代码支持该 schema version；当前代码拒绝比自身更新的数据库；
- 恢复后先在隔离数据目录运行 list/check/fetch 验证，不直接覆盖唯一正式副本；
- 不手工修改状态、revision、路径或 locator 来“修好”数据库；确需数据修复时先备份，并以迁移/维护工具和测试表达规则。

### 13.3 启动维护

每次 Runtime 启动当前会：

- 打开/迁移 SQLite；
- 把遗留 submitting 标记为 `SUBMISSION_OUTCOME_UNKNOWN`；
- 清理超过保留时间的 `.part`；
- 可选调度过期 terminal Job；
- 处理 cleanup queue，文件删除失败会记录并留待重试。

维护逻辑失败不应泄漏路径或秘密。正式 retention 默认关闭；任何改变默认删除行为的方案都需要显式决策和用户文档。

### 13.4 常见故障定位

| 现象 | 先检查 | 不要做 |
|---|---|---|
| `MODELSCOPE_TOKEN_MISSING` | Host 环境和 Server 重启；本地 list 是否仍可用 | 把 Token 作为 Tool 参数传给 Agent |
| `SUBMISSION_OUTCOME_UNKNOWN` | Job、时间和安全 request ID | 自动重提相同请求 |
| check 网络/HTTP 错误 | retryable、retry_after、原 JobStatus | 手工改成 failed 或重新提交 |
| `UPSTREAM_STATUS_UNKNOWN` | 脱敏真实响应和 Provider 状态文档 | 猜测为 running/succeeded/failed |
| fetch partial/failed | 每图 last_error、磁盘、权限、上限 | 删除 available 文件后全量重下 |
| 文件存在但元数据缺失 | 再次 fetch 触发 inspect/repair | 手工拼绝对路径写数据库 |
| `CONCURRENT_MODIFICATION` | 同 Job 并发入口和最新 revision | 关闭 revision 检查 |
| `PERSISTENCE_ERROR` | 磁盘、权限、schema、锁和 SQLite 状态 | 向 Agent 返回原始 SQL/路径异常 |
| Host 找不到文件 | Host 与 Server 的文件可见性、Artifact Root 挂载 | 默认改为 base64 或放宽路径控制 |

## 14. 版本、构建与发行维护

### 14.1 版本来源

- 发布版本定义在 [`pyproject.toml`](../../pyproject.toml)；
- package 运行时优先从 `importlib.metadata` 读取安装版本；源码未安装 fallback 必须与发布版本同步；
- 当前正式用户安装来源为仓库 `main`，Git URL、console script 和预发布依赖参数必须与 README 同步；
- CHANGELOG 添加对应版本与真实日期；
- README 中的验证状态只报告实际完成的证据。

不要在多个位置静默产生不同版本。版本准备变更至少检查：

```text
pyproject.toml
src/modelscope_image_gen/__init__.py fallback
CHANGELOG.md
uv.lock（项目元数据）
README.md / README.zh-CN.md Git install command
```

### 14.2 构建内容

wheel/sdist 不得包含：

- `legacy/`；
- `.env`、Token、数据库、WAL/SHM；
- 生成图片或本地 outputs；
- 测试中的秘密或未脱敏真实响应；
- 开发缓存和临时文件。

必须包含运行需要的 migration SQL 和 `py.typed`。修改 package data、构建后端或目录时，不能只依赖源码测试，必须审计构建内容并隔离安装。

### 14.3 发布证据

发布报告分别说明：

- Ruff/ty/pytest/build 是否通过；
- Windows 和 Ubuntu CI 是否实际通过；
- wheel 是否实际隔离安装并运行 console script；
- 远端 Git URL 是否实际通过 uvx 构建并运行 console script；
- stdio 是否实际启动；
- 官方内存 Client 是否通过；
- 哪些真实 MCP Host 实际验证；
- 哪些真实 ModelScope 工作流实际验证；
- 当前 Git 安装验证针对哪个 ref/commit；未来 PyPI 或 MCP Registry 是否仍只是可选计划。

依赖升级，尤其是 MCP SDK 从 beta 到 stable 或大版本变化，应独立成变更，避免与领域或 Pydantic schema 改动混在一起。

## 15. 文档维护规则

### 15.1 变化应更新哪里

| 变化 | 主要更新位置 |
|---|---|
| 用户安装、配置、工具使用或故障恢复 | `README.md` + `README.zh-CN.md` |
| 安全支持、秘密、文件系统和报告方式 | `SECURITY.md` |
| 当前架构、变更路径、维护规则 | 本手册 |
| 全体 Agent 必须遵守的新强制入口规则 | `AGENTS.md`，并保持简洁 |
| 重构之后的重大产品/架构决策 | `docs/decisions/NNNN-*.md` |
| 待发布与已发布的用户可见变化和兼容边界 | `CHANGELOG.md` |
| 精确 Tool schema | Pydantic DTO、Registry、契约测试；文档只做用户级摘要 |
| 精确配置默认值 | `Settings` 为代码事实源，`.env.example`/README 同步 |
| 可自动证明的不变量 | 测试、CI、架构门禁 |

### 15.2 避免多份真相

- 不在本手册复制完整 JSON schema；链接 DTO 和契约测试，并解释改变它的影响。
- 不在多个文档人工维护完整错误码表；以 Domain enum 为事实源，文档只解释稳定语义和恢复方式。
- 不把当前测试数量当作永久验收标准；记录验证结果时附版本或日期。
- 不把历史 `docs/rebuild` 修改成当前维护文档；使用取代记录连接历史与现状。
- README 面向用户和操作者，不塞入内部类图和每个模块细节。
- 代码注释不替代决策记录；决策记录也不替代清晰代码与测试。

### 15.3 文档修改也需要验证

文档变更至少检查：

- 相对链接真实存在；
- fenced code block 配对；
- 当前文件名、Tool 名称、命令和版本准确；
- 中英文用户材料没有语义冲突；
- “已通过”“已发布”“真实验证”等声明有对应证据；
- 历史、当前、计划和提案状态清楚；
- 没有复制 Token、真实签名 URL、个人 prompt 或本地敏感路径。

## 16. 项目一致性审计

局部任务都通过测试，项目仍可能在长期维护中发生累计漂移。出现大版本准备、连续多次跨层变更、重大依赖升级或新 Agent 难以解释主路径时，应执行一次一致性审计。

### 16.1 产品与语义

- 五工具是否仍各自拥有清晰且不重复的能力？
- 默认异步路径是否仍然优于阻塞入口并被文案正确引导？
- 本地 Job、上游 Task、产物和单次操作是否仍被区分？
- 是否出现新的隐式状态、布尔组合或无法恢复的中间事实？
- 多图片、partial 和幂等是否仍贯穿所有入口？

### 16.2 架构与代码

- Domain/Application/MCP 的禁止依赖是否仍被 AST 测试覆盖？
- Bootstrap 是否仍是唯一 composition root？
- Provider、Repository、Artifact 和 Presenter 是否各自只解释自己的事实？
- 是否出现第二套轮询、下载、路径、错误或 next-action 逻辑？
- `Any`、通用 helpers、布尔开关或中央 service 是否开始侵蚀边界？
- 代表性黄金路径是否仍是新代码实际遵循的模式？

### 16.3 数据与安全

- migration 是否能从所有已发布 schema 顺序升级？
- list 和日志是否新增了敏感字段？
- Artifact 路径、junction 和原子提交测试是否仍覆盖支持平台？
- retention、cleanup queue 和文件修复是否仍保持数据库/文件协调？
- build、wheel、备份或测试 fixture 是否可能包含正式数据或秘密？

### 16.4 契约与体验

- Tool schema、description、annotations、server instructions、README 是否一致？
- structured content、TextContent、`ok` 和 `isError` 是否仍表达同一事实？
- 每个结果是否仍告诉 Agent 当前状态和安全下一步？
- 未知提交、未知状态和 partial 是否仍不会诱导危险重试？
- 至少一个真实 Host 是否能理解当前 schema 和文件路径？

### 16.5 知识连续性

- 当前代码是否存在未记录的重大方向偏移？
- Accepted/Superseded 决策关系是否清楚？
- 本手册页首基线和实现地图是否仍准确？
- 是否有“临时”分支已经失去退出条件？
- 新 Agent 是否能不依赖旧会话完成第 3.2 节理解快照？

审计发现的问题应进入明确的修复或决策入口，不要只留在一次审查对话中。

## 17. Agent 交接规范

### 17.1 每次交付必须区分

- 自动化测试通过；
- wheel 实际构建/安装通过；
- 真实 stdio 通过；
- 官方内存 Client 通过；
- 真实 Host 通过；
- 真实 ModelScope 通过；
- 远端 Git + uvx 安装通过；
- 可选发行渠道是未开始、准备中还是实际完成。

### 17.2 标准交接模板

```markdown
## 目标与结果

本次解决了什么，最终行为是什么。

## 全局影响

涉及 submit/check/fetch/list/generate 中哪些路径；
涉及哪些领域、应用、Provider、SQLite、Artifact、MCP、安全或运维边界。

## 决策与一致性

采用什么方案以及为什么；
保持了哪些不变量；
是否改变既有决策或新增 ADR；
是否对开发者建议提出过重要修正。

## 关键文件

下一任 Agent 应从哪些实现和测试入口阅读。

## 验证证据

实际执行的命令、结果、平台和测试数量。

## 未验证事项

未运行的 live、真实 Host、wheel、迁移、CI 或发布步骤。

## 数据、兼容性与安全

schema、旧 Job、文件、Token、日志、路径和外部副作用的影响。

## 风险与重新评估条件

剩余风险、假设、临时偏移及其退出条件。

## 永久知识回写

更新的 AGENTS、维护手册、决策、README、SECURITY、CHANGELOG 和测试。

## 工作区说明

保留了哪些不属于本任务的已有改动。
```

### 17.3 禁止夸大

不得使用以下替代关系：

- “代码存在”替代“能力可靠”；
- “测试通过”替代“真实外部系统通过”；
- “CI 有配置”替代“目标平台实际 run 通过”；
- “存在 Git 安装命令”替代“远端 Git 实际可构建运行”；
- “本机源码可运行”替代“远端 Git 或 wheel 用户路径可运行”；
- “一张真实图片成功”替代“所有模型/多图由上游保证”；
- “当前会话理解了”替代“永久项目知识已更新”。

## 18. 完成定义

一次维护任务只有在以下条件满足时才算完整：

1. 根因而非仅表面症状得到处理；
2. 修改位于正确的事实和职责边界；
3. 所有相关入口、失败、取消、恢复、并发和部分成功路径已经相称检查；
4. 第 7 章相关不变量得到保留，或已通过正式决策改变；
5. 没有创建第二套工作流、状态、错误、路径或事实来源；
6. 代码风格与当前设计语言一致，必要偏离有明确理由；
7. 数据、兼容性、安全、隐私和运维影响已经处理；
8. 针对性测试和相称全局门禁已经运行；
9. live、Host、wheel、平台和发布证据被真实区分；
10. 用户材料、维护文档、决策和自动护栏已经同步；
11. 用户已有改动得到保护；
12. 下一任 Agent 不依赖本次会话也能恢复新的项目状态。

## 19. 当前基线备注

截至页首复核基线：

- package 版本为 `0.2.1`；
- Python 范围为 `>=3.14,<3.15`；
- MCP SDK 固定为 `2.0.0b1`，预发布依赖变化需要独立验证；
- SQLite schema version 为 1；
- Tool 集合固定为五项；
- CI 配置覆盖 Windows 和 Ubuntu；
- GitHub Actions 有意跟随 `actions/checkout@v7` 与 `astral-sh/setup-uv@v8` 的稳定 major 更新，不固定 commit SHA；实际 uv binary 仍固定为 `0.11.28`；
- 自动测试基线为 39 个默认测试及 1 个显式 live 测试；
- CHANGELOG 将当前 `0.2.1` 源码变化置于 `Unreleased`，并记录了真实 ModelScope、两个真实 stdio Host、wheel、远端 Git 安装和产物一致性的既有验证；
- [`ADR 0001`](../decisions/0001-use-git-source-distribution.md) 已确认 GitHub 源码加 `uvx --from` 为当前正式用户路径，本地 checkout 为开发路径；
- README 默认跟随 `main`，当前因 MCP SDK `2.0.0b1` 必须传入 `--prerelease=allow`；
- PyPI 上的 `modelscope-image-gen-mcp` distribution 属于另一个项目；仓库不提供裸 `uvx modelscope-image-gen-mcp`，也不保留指向该 distribution 的 `server.json`；
- PyPI、TestPyPI、MCP Registry 和 GitHub Release 已延期，不属于当前 `0.2.1` 收尾定义；wheel/sdist 构建和隔离安装仍是质量门禁。

这些状态会变化。后续维护者必须查看当前代码、CI、发布平台和最新 CHANGELOG，不得把本节历史复核信息当作永久现状。

## 20. 最终维护原则

1. 先恢复项目全局，再处理当前局部。
2. 先区分事实层，再决定状态和错误归属。
3. 先确认根因，再选择修改点。
4. 默认扩展既有纵向主路径，不建立平行实现。
5. 最小改动必须是最小完整改动，不是最少文件。
6. 对开发者目标负责，同时保持有证据的独立判断。
7. 尊重已接受决策，同时允许通过正式程序吸收新事实。
8. 用自动化保护稳定不变量，用 live/Host 证明模拟无法证明的事实。
9. 对未验证事项诚实，对敏感数据克制，对不可逆变化谨慎。
10. 每次交付都要让项目比接手时更容易被下一任 Agent 正确理解。
