# ModelScope Image Gen MCP 重构方向

## 文档状态

- 状态：已确认
- 适用目标：重构后的 V1
- 目标运行时：Python 3.14
- 目标协议与 SDK：MCP Python SDK v2.0
- 项目管理与构建：uv + `uv_build`
- 类型检查：ty

本文是本次平地重构的方向性契约。后续领域模型、配置、存储、MCP 接口和代码组织不得偏离本文；如需改变本文中的已确认决策，必须先更新本文并说明理由。

## 1. 重构目标

新系统是一个本地优先、ModelScope 专用、面向 Agent、可靠处理长耗时任务的 MCP v2 图像生成服务。

它的核心价值不是简单封装一次 ModelScope HTTP 请求，而是：

- 为 Agent 提供清晰、稳定、可恢复的图像生成工作流。
- 将上游异步任务转换为明确的本地领域模型与状态变化。
- 提供机器可读的结果、错误、重试信号和下一步动作。
- 安全管理本地任务状态与生成产物。
- 支持通过 PyPI/`uvx` 安装，并通过 stdio 接入 MCP Host。

## 2. 产品边界

### 2.1 V1 明确包含

- 文本生成图片。
- ModelScope 单一上游提供商。
- 提交图像生成任务。
- 查询并刷新任务状态。
- 下载并持久化生成结果。
- 跨 MCP 调用和进程重启恢复任务。
- 安全、受约束的本地输出目录。
- 结构化状态、结果和错误语义。
- 请求 ID、阶段信息和基本可观测性。
- stdio MCP v2 服务。
- 可通过 PyPI/`uvx` 安装的 Python 包。

### 2.2 V1 明确不包含

- 参考图生图。
- 图片编辑。
- 多提供商支持。
- Provider 插件系统。
- Web 或桌面管理界面。
- 分布式任务队列。
- 远程 Streamable HTTP 部署。
- OAuth 或多租户认证。
- 尚未落地的 MCP Tasks 扩展。
- 为 MCP v1 保留独立实现或兼容层。
- 为旧内部代码结构提供兼容 API。

任务取消只有在后续确认 ModelScope 上游存在可靠取消契约时才允许进入 V1；不能用本地状态伪装上游任务已取消。

## 3. 核心输出决策

V1 虽然只做文生图，但领域层从第一天起必须将生成结果建模为：

```python
list[GeneratedImage]
```

该决策表达的是“一次生成任务可以产生零到多张图片”，而不是承诺 V1 的每个 ModelScope 模型都会返回多图。

必须遵守：

- 上游当前只返回一张图片时，也转换为单元素列表。
- 不在领域模型中使用 `image_url`、`output_path` 等单数顶层字段表达最终结果。
- MCP 返回、持久化 schema 和文件存储接口必须能够表达多张图片。
- 未完成或失败状态可以没有图片；成功终态不得使用空列表，上游宣告成功却没有图片时必须转换为明确错误。
- 每个 `GeneratedImage` 拥有独立标识和顺序，并能够表达上游来源引用、媒体信息、文件状态和本地产物信息；具体字段和敏感信息保留规则由后续文档决定。

`GeneratedImage` 的完整字段将在 `03-domain-model-and-behavior-map.md` 中定义。

## 4. 资产角色

### 4.1 当前仓库：主要语义源

当前实现是重构的主要业务语义来源。

继承：

- `prompt`、`negative_prompt`、`seed`、`model`、`size` 等生图能力。
- 提交、轮询、下载和保存的完整任务语义。
- 长任务需要拆分为异步工作流的产品判断。
- 轮询间隔、退避、最大尝试次数和分阶段 HTTP 超时经验。
- `stage`、`reason_code`、`retryable`、`retry_after_seconds`、`request_id` 等错误语义。
- 本地任务需要跨多次 MCP 调用恢复。
- Agent 需要明确的状态、建议等待时间和下一步动作。
- 阻塞式便利能力对简单调用方有价值。

不继承：

- Mixin 组合式服务类。
- 大量 `Any`、类型检查抑制和隐式属性契约。
- 手写 MCP 工具 schema 和集中式工具名分发。
- 模块导入阶段创建全局 Settings、Service 和网络相关对象。
- JSON 文件任务数据库。
- 阻塞和异步流程各自维护一套提交、轮询、下载逻辑。
- 各工作流重复实现 HTTP 异常转换。
- 模型可控制任意 `output_dir` 的文件写入方式。
- 当前目录结构和历史兼容导出模块。
- MCP v1 底层 Server API。

### 4.2 ModelScope 官方 API：上游事实来源

ModelScope 官方 API 和经过脱敏的真实响应决定：

- 请求与响应格式。
- 上游任务状态及状态转换。
- 错误响应和限流行为。
- 是否支持任务取消。
- 图片数量、格式和尺寸信息。
- 远程结果 URL 的有效期与访问要求。

旧代码只能作为实践经验，不能覆盖真实上游契约。实现阶段必须建立脱敏响应 fixture，并提供需要显式 Token 才会运行的可选在线集成测试。

### 4.3 原始参考项目：历史参考源

README 中提及的原始项目是历史参考源，不是新系统架构权威。

可以从中提取当前仓库遗漏的业务行为和历史踩坑经验；不继承其代码结构、技术栈或接口设计。若未发现额外业务语义，不要求迁移其实现。

### 4.4 体验灵魂源

本项目没有视觉 UI 灵魂源。它的体验灵魂是 Agent 使用体验：

- 工具用途和副作用清楚。
- Agent 能准确判断任务是否完成。
- Agent 知道下一步应该调用什么。
- 长任务不会强迫一次工具调用无限等待。
- 失败能够区分是否可重试以及何时重试。
- 结果同时便于模型理解和 Host 程序消费。

## 5. 技术方向

以下决策已经锁定：

- 使用 Python 3.14 的标准 GIL 构建。
- 使用 uv 管理 Python、依赖、锁文件、构建和发布。
- 使用 `uv_build` 构建纯 Python 包。
- 使用 MCP Python SDK v2.0，不实现 v1 兼容层。
- v2 稳定版发布前，开发环境精确固定到经过验证的 beta 版本。
- 使用 ty 作为唯一类型检查器，替代 Pyright。
- 使用 Ruff 负责格式化和静态规则检查。
- 使用 pytest 作为测试框架。
- 采用 `src/` package layout。

SQLite、Pillow 和 platformdirs 已在后续技术与存储决策中证明必要并锁定；具体版本、职责和边界以 `02-technology-stack-decisions.md` 与 `04-config-and-storage-schema.md` 为准。

## 6. 工程边界

目标依赖方向：

```text
MCP 适配层
    ↓
应用用例层
    ↓
领域模型
    ↑
Provider / Repository / Artifact Store 端口
    ↑
ModelScope / SQLite / 本地文件系统适配器
```

必须遵守：

- 领域层不得导入 MCP、httpx、SQLite、Pillow 或 pydantic-settings。
- MCP 工具不得直接调用 ModelScope API。
- MCP 工具不得直接执行文件系统写入。
- ModelScope 原始响应不得直接作为领域对象或 MCP 返回。
- 所有任务状态变化必须经过显式状态规则。
- MCP DTO、领域对象和上游响应模型必须区分。
- Provider 接口允许替换实现，但 V1 不建设插件发现机制。
- HTTP Client、任务仓库和其他生命周期资源通过 MCP lifespan 创建与释放。
- 预期业务失败转换为稳定领域错误；未预期异常在边界统一净化。

## 7. 任务语义约束

- 本地 Job ID 与 ModelScope Task ID 是不同标识。
- 本地 Job 是本系统事实来源，上游 Task 是其关联的外部执行记录。
- “本次轮询预算耗尽”不等于“上游任务失败或终止”。
- 未确认上游失败前，任务必须能够在后续调用中继续刷新。
- 上游成功与本地产物已经保存是两个不同事实。
- 下载或保存失败不得抹去已经成功的上游生成结果。
- 同一结果的重复获取应当尽量幂等。
- 状态、时间和错误必须可持久化并在进程重启后恢复。

完整状态机将在 `03-domain-model-and-behavior-map.md` 中定义。

## 8. 文件与隐私边界

- 输出根目录由服务器配置决定，不由模型自由指定。
- V1 工具不接受输出目录、绝对路径或自定义最终文件名；产物位置完全由 Artifact Store 在输出根目录内决定。
- 所有最终路径必须在写入前经过规范化和根目录边界验证。
- 图片保存应采用临时文件加原子替换，避免留下半写入产物。
- API Token 只来自服务器配置，不得成为 MCP 工具参数。
- Token、Authorization Header、签名 URL 和其他凭据不得写入日志或错误返回。
- 默认不记录完整 prompt；如未来支持诊断日志，必须显式选择并清楚标注隐私影响。
- 持久化数据中的 prompt、远程 URL 和错误响应必须有明确保留与清理策略。

## 9. MCP 产品方向

V1 以工具能力为主，不为了展示 MCP 能力而增加 Prompts 或 Resources。

异步工作流是默认路径：

```text
提交任务 → 查询/刷新状态 → 获取并保存结果
```

阻塞式 `generate_image` 作为便利能力保留在产品方向中，但必须满足：

- 在异步三段式竖切完成后实现。
- 复用相同应用用例和领域状态机。
- 不再维护独立的提交、轮询、下载实现。
- 具备明确最大等待时间，并正确响应取消和 Host 超时。
- 工具描述必须引导 Agent 默认选择异步工作流。

工具名称、输入、输出以及最终是否暴露阻塞式工具，将在 `01-product-and-information-architecture.md` 与 `05-mcp-interface-contract.md` 中最终确认。

## 10. Legacy 归档规则

现有实现将在正式新建骨架前归档到：

```text
legacy/v0.1.0/
```

归档前必须创建明确的 Git 提交或 tag。

归档目录：

- 是业务语义、测试样本和反例来源。
- 只保留旧核心源码、入口、双语 README、旧 CI workflow 和经过筛选的高价值行为测试。
- 不保存旧 `pyproject.toml`、`uv.lock`、Python 3.12 配置或旧 `.gitignore`；完整旧环境通过 Git tag 追溯。
- 不属于新项目的 uv workspace。
- 不参与根项目构建、打包、测试、格式化、Lint 或类型检查。
- 不得被新代码 import。
- 不得成为复制旧实现的捷径。

`legacy/README.md` 必须说明归档版本、来源、用途、可继承行为和禁止继承内容。

## 11. 禁止事项

- 不要逐行翻译旧代码。
- 不要将旧的四个 MCP 工具视为不可改变的接口事实。
- 不要为了“通用性”提前建设多 Provider 插件系统。
- 不要使用 MCP v1 API 或建立 v1/v2 双实现。
- 不要让 MCP、Provider 或存储模型互相充当对方的数据模型。
- 不要把所有流程重新堆进入口文件或单个 Service 类。
- 不要把持久化实现、文件系统或 HTTP 异常直接泄露给 Agent。
- 不要让模型控制任意绝对路径。
- 不要把轮询超时写成不可恢复的任务终态。
- 不要假设一次任务永远只产生一张图片。
- 不要在没有真实 API 证据时假设 ModelScope 支持取消、多图或永久结果 URL。
- 不要为尚未确认的后续功能污染 V1 领域模型。

## 12. 第一阶段验收

第一条完整竖切必须满足：

- Python 3.14 环境可通过 uv 同步。
- MCP v2 stdio 服务可启动并被内存 Client 与真实 MCP Host 调用。
- `ruff format --check`、`ruff check`、`ty check` 全部通过。
- 领域、应用、Provider、持久化、文件存储和 MCP 契约测试通过。
- `uv build` 成功生成可安装分发物。
- 任务可以提交，并在进程重启后继续查询。
- 成功任务返回 `list[GeneratedImage]`。
- 结果可以安全保存到配置的输出根目录。
- 轮询预算耗尽后仍可继续刷新任务。
- 下载失败不会丢失已经成功的上游结果。
- 日志、结构化返回和持久化错误不泄露 Token 等敏感信息。
- 至少完成一次显式启用的真实 ModelScope 样本验证。

## 13. 后续文档

本文确认后，按以下顺序继续：

1. `01-product-and-information-architecture.md`
2. `02-technology-stack-decisions.md`
3. `03-domain-model-and-behavior-map.md`
4. `04-config-and-storage-schema.md`
5. `05-mcp-interface-contract.md`
6. `06-core-organization.md`
7. `07-agent-experience.md`
8. `08-implementation-brief.md`

后续文档负责细化本文，不得静默修改本文已确认的产品边界。
