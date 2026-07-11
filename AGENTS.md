# ModelScope Image Gen MCP Agent 入口

本文件适用于整个仓库。任何 Agent 在进行非机械性分析、设计或修改前，必须先恢复项目全局上下文，并把自己视为项目一致性的临时托管者，而不只是当前指令的执行器。

## 必读顺序

1. 完整阅读[面向会话型 Agent 的长期项目连续性元指南](docs/agent-project-continuity-meta-guide.md)。
2. 完整阅读[项目维护与交接手册](docs/maintenance/README.md)。
3. 根据任务阅读相关的 `docs/rebuild/00`–`07` 专项契约；`08` 是已经完成的重构实施交接，不是当前开发计划。
4. 阅读任务对应的实现、直接调用路径和测试。不得只阅读准备修改的单个文件。
5. 面向用户的行为与运维体验以 `README.md`、`README.zh-CN.md`、`SECURITY.md` 和 `CHANGELOG.md` 为补充材料。

如果只是回答问题或进行只读诊断，应按风险缩小阅读范围，但结论不得超出已经掌握的证据。

## 开始工作前

- 检查当前分支、`git status`、近期提交和用户已有改动；保护所有不属于本任务的工作。
- 用“目标、根因、必须保持、非目标、成功证据”形成变更命题。
- 判断变更是局部实现、跨边界行为、公开契约、数据迁移，还是产品/架构方向变化。
- 对产品工作流、领域状态、应用编排、Provider、SQLite、Artifact、MCP wire、Agent 体验、安全、运维、测试和文档做相称的全局影响扫描。
- 如果开发者建议遗漏全局影响、违反既有不变量或只处理症状，必须先给出证据和替代方案。不得机械服从，也不得为了表现自主性而无依据反对。

## 项目不可静默破坏的基线

- 默认产品路径是 `submit → check → fetch`；`generate` 只是复用这些用例的阻塞便利入口。
- 本地 `GenerationJob` 是任务事实来源；上游 Task 是外部执行记录；上游成功与本地产物可用是两层事实。
- 外部提交前必须先持久化 `submitting`。提交结果可能不确定时不得自动重提。
- 网络错误、未知 Provider 状态、本地等待到期和调用取消不得伪造成上游 Job 失败或取消。
- 一次 Job 始终支持有序多图片；每张图片独立落盘、失败和重试。不得退化为只处理第一张图片。
- available 产物必须幂等；重复 fetch 不得重复下载或覆盖。已原子提交的图片应能在取消或数据库更新失败后恢复元数据。
- Agent 不得控制输出目录和文件名。路径必须由受控 ID 派生并限制在 Artifact Root 内。
- Provider 拥有 HTTP 请求、上游响应解释和图片流生命周期；Artifact Store 不认识 URL 或 HTTP，不更新 Job；Repository 不解释 Provider 响应。
- Domain 不依赖框架；Application 不依赖 Infrastructure 或 MCP；MCP Adapter 不依赖具体 Infrastructure；`bootstrap.py` 是唯一 composition root。
- MCP 的 `ok` 表示工具操作是否成功，不等于 Job 是否成功。TextContent 与 structured content 必须表达同一事实。
- Token、Authorization、prompt、Provider locator、原始上游正文、内部异常和不应暴露的本地路径必须遵守现有隐私边界。
- stdout 只承载 MCP wire，日志写 stderr；导入 package 和 `--version` 不得创建运行时资源或要求 Token。
- `legacy/` 是只读历史语义与反例资产，不参与根项目构建、测试和导入。除非任务明确要求维护归档说明，否则不要修改它。

这些条目表达长期不变量或当前已接受的 V1 契约。需要改变时，必须遵循维护手册中的决策协议，而不是通过局部代码静默偏移。

## 实现方式

- 追求最小完整改动，不追求机械意义上的最少文件。
- 先判断规则的所有者，再选择修改点；不要在最近的 handler、presenter 或适配器里添加业务特例。
- 优先扩展健康的现有主路径，不创建第二套 submit、poll、download、状态、错误或路径逻辑。
- Domain 使用不可变、显式的值对象和状态转换；Application 使用端口与封闭 outcome；MCP DTO 只存在于适配层。
- 不创建无明确边界的 `utils.py`、`helpers.py`、中央 `service.py` 或跨层 `Any` 数据通道。
- 新增重大依赖、公开 Tool、状态、错误语义、数据格式、Provider、传输模式或信任边界前，先创建或修订正式决策。
- 任何已确认的新方向都应同步到决策、维护文档、代码、测试和用户材料；不得留下只有当前会话知道的设计变化。

## 验证基线

按风险先运行针对性测试，再运行相关全局门禁。发布级基线为：

```text
uv lock --check
uv sync --locked --all-groups
uv run ruff format --check
uv run ruff check
uv run ty check
uv run pytest
uv build --no-sources
```

Provider 变化需要 MockTransport 证据；SQLite 变化需要 migration、round-trip、restart 和 concurrency 证据；Artifact 变化需要真实图片与路径攻击证据；MCP 变化需要 schema、内存 Client 和必要的真实 Host 证据。真实 ModelScope 测试必须显式 opt-in，不能把模拟通过报告为真实上游通过。

## 完成交接

最终交付必须说明：

- 完成的目标和全局影响；
- 关键决策、保持或改变的不变量；
- 关键文件和测试证据；
- 未运行的 live、Host、迁移、wheel 或发布验证；
- 兼容性、数据、安全和运维影响；
- 已知风险、假设、临时偏移和重新评估条件；
- 更新了哪些永久知识；
- 是否保留了用户已有改动。

会话可以结束，但任何会影响下一任 Agent 判断的知识都必须留在项目中。
