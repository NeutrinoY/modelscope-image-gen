# 0001：当前正式安装路径采用 Git 源码与 uvx

- 状态：Accepted
- 日期：2026-07-12
- 决策者：NeutrinoY
- 取代：`docs/rebuild/00`、`02`、`05`、`08` 中将 PyPI 与 MCP Registry 视为当前 V1 必交付发行路径的部分
- 被取代：无

## 背景

项目已经完成 `0.2` 重构和 `0.2.1` 可靠性加固，但 PyPI 上的 `modelscope-image-gen-mcp` distribution 属于另一个项目。继续保留同名 PyPI 安装说明或 `server.json` 会把本仓库与无关发行物错误关联。

当前项目规模较小，主要面向开发者和高级用户。`uvx --from git+https://...` 已能直接从 GitHub 获取、构建、隔离安装并运行本仓库的 console script，不要求用户预先 clone 源码，也不要求项目维护者立即建立 PyPI/TestPyPI 账号、Trusted Publisher 和 Registry 发布流程。

2026-07-12 已从远端 `rebuild/v0.2.0` 分支实际验证：加入 `--prerelease=allow` 后，`uvx --from` 成功构建提交 `2a114ff` 并运行 `modelscope-image-gen-mcp --version`，返回 `0.2.1`。该参数当前必需，因为 MCP SDK 仍固定为 `2.0.0b1`。

## 必须保持的约束

- 用户必须能通过一份标准 MCP Host command/args 配置启动 Server。
- Git 安装必须指向本仓库，不得与同名第三方 PyPI distribution 混淆。
- `MODELSCOPE_SDK_TOKEN` 继续只通过 Host 环境提供。
- Job、SQLite 和 Artifact 必须保存在用户数据目录，不得依赖 uvx 工具环境寿命。
- wheel/sdist 构建、隔离 wheel smoke test 和 package metadata 审计继续作为质量门禁。
- 本地源码检出仍是开发和调试路径，但不再是普通用户的唯一安装路径。
- PyPI、MCP Registry 和 GitHub Release 的未来状态必须分别陈述，不能从源码或构建成功推断已经发布。

## 方案

### 方案 A：立即协调或更换 PyPI 名称

可以获得传统的 `uvx <distribution>` 体验和未来 Registry 接入，但会立即引入名称决策、双索引账号、Trusted Publishing、发布运维和兼容别名工作。当前用户规模尚不足以证明这些成本必要。

### 方案 B：只要求用户手工 clone 源码

最容易维护，但用户需要管理本地路径、同步和环境，MCP Host 配置也依赖固定 checkout 位置，不适合作为唯一公开安装方式。

### 方案 C：Git 源码作为 uvx package source

用户只需安装 uv，并在 Host 中配置 Git URL。首次运行由 uv 获取和构建，后续复用缓存；开发者仍可使用本地 checkout。缺点是首次运行依赖 GitHub 和 package index，移动分支也弱于不可变发行物的可复现性。

## 决策

采用方案 C：当前正式用户安装路径为 GitHub 源码加 `uvx --from`，默认跟随 `main`：

```text
uvx
--prerelease=allow
--from
git+https://github.com/NeutrinoY/modelscope-image-gen.git@main
modelscope-image-gen-mcp
```

本地源码检出保留为开发路径。默认文档不加入 `--refresh`，避免每次 Host 启动都强制刷新网络缓存；需要立即更新时由操作者显式执行 refresh。

PyPI、TestPyPI、MCP Registry 和 GitHub Release 当前全部延期，不属于 `0.2.1` 收尾定义。仓库删除指向第三方 PyPI distribution 的 `server.json`；未来只有在本项目拥有可验证的发行物后才能重新建立 Registry manifest。

## 后果

### 正面

- 立即获得无需本地 checkout 的一条命令安装体验。
- 不再被 PyPI 名称冲突阻塞，也不需要维护发布凭据。
- GitHub 仓库成为源码身份和安装来源的单一入口。
- package 构建能力与未来 PyPI 选择仍然保留。

### 代价

- 首次运行需要 GitHub、依赖索引和本地构建时间。
- `main` 是移动目标；不同时间首次安装可能得到不同提交。
- uv 缓存可能使分支更新不会在每次启动时立即生效。
- 当前必须显式允许 MCP SDK 的预发布依赖。
- 没有 PyPI distribution 时不能宣称已经具备 MCP Registry 的标准包发行路径。

### 兼容性与安全

- console script 和 Python import package 不变化。
- 现有本地 checkout Host 配置继续有效。
- 默认跟随 `main` 符合当前高级用户定位；需要可复现安装的操作者可以自行把 `main` 替换为受信任的 tag 或 commit。
- 用户应核对 Git URL owner 为 `NeutrinoY`，避免从不受信任的 fork 执行源码。

## 实施与迁移

1. 将双语 README 的普通用户 Quick Start 改为 Git + uvx，并把本地 checkout 移到开发路径。
2. 在 SECURITY 中明确官方源码身份、同名 PyPI 风险和移动分支的信任边界。
3. 删除当前 `server.json`，并从维护手册的版本同步清单中移除它。
4. 在 CHANGELOG 记录安装路径变化和 Registry manifest 移除。
5. 合并重构分支到 `main` 后，从远端 `main` 再运行一次完整 uvx smoke test。
6. 保留 wheel/sdist 构建与隔离安装门禁。

## 验证

- Git 分支 URL 可被 uv 获取并构建。
- `uvx --prerelease=allow --from <git-url> modelscope-image-gen-mcp --version` 返回当前版本。
- MCP Host 使用同一 args 形态能够发现五个工具。
- 无 Token 时 Server 可以启动，本地 list 和已持久化终态仍可读取。
- Job、数据库和图片不写入 uvx 工具环境。
- README 不提供裸 `uvx modelscope-image-gen-mcp` 或第三方 PyPI 安装命令。
- 仓库不存在声称当前 PyPI/Registry 已发布的 manifest 或文案。

远端 `main` smoke test 和真实 Host 验证只能在分支合并后完成，不能由本地或重构分支测试替代。

## 永久知识同步

- 双语 README
- SECURITY
- CHANGELOG
- 项目维护与交接手册
- 决策索引
- CI 与 package smoke test

历史重构文档保持原貌，由本决策建立取代关系。

## 重新评估条件

出现以下任一条件时重新评估 PyPI 或其他不可变发行渠道：

- 普通用户需要更短的安装命令或更快的首次启动；
- MCP Registry 成为主要发现入口并要求受支持的 package registry；
- 企业或离线环境需要不可变、可镜像的发行物；
- `main` 移动目标造成可复现性或回滚问题；
- 项目拥有合适且稳定的 PyPI distribution 名称；
- MCP SDK 稳定版发布并完成兼容验证。
