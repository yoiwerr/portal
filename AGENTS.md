# Portal：模型工作入口

本仓库的当前架构快照更新于 2026-10-28，包含工作区改动，不表示已发布到服务器。

2026-10-28 增补：最新产品边界见 [dude 架构基线](dude/docs/dude-architecture-baseline.md) 与更新后的 PRODUCT。`dude/dude-orchestrator/` 已提供独立 TypeScript API、Project Brief 和成对文档持久层；Pi、聊天、React 和网页切流尚未接入。默认运行仍是下面描述的 Python 链路。新服务以 `package.json` + `package-lock.json` 锁定依赖，启动与隔离测试见其 README。

## 先读什么

1. 开始任务先检查 `git status --short` 和任务相关 diff，保护已有修改。
2. 读 [当前项目认知](docs/project-context.md)：项目边界、运行拓扑、路由、数据库、已知缺口与验证入口。
3. 按任务定位 [全文件索引](docs/project-file-index.md)，不要把依赖缓存、临时预览或历史教程当成运行源码。
4. dude 任务再读 [产品定义](dude/PRODUCT.md)、[模块地图](dude/CLAUDE.md) 和 [00–08 板块](dude/docs/product-modules.md)。

## 不应误判的事实

- 活跃产品是 dude（源码 `dude/`，原名 Alfred / MakeItSpecific）和 Journal。
- 更名兼容：现有数据库 `alfred`、浏览器 `alfred_*` 登录键和 JWT issuer 保留；新入口 `/dude/`，旧 `/alfred/` 仍代理。服务器 Git 拉取不会自动迁移旧目录中的忽略文件，见 [更名迁移](docs/dude-rename.md)。
- dude-admin 是 dude 的 Go 认证/管理服务，不是聊天代理；Python 和 Go 属于同一产品。
- ChatLab 的 `ChatHistoryAnalyst/` 已停用并另存本地快照，不参与根级 Compose 和默认开发启动；源码保留，不是已删除或已建立独立远程仓库。
- 根级 Compose 管理共享 PostgreSQL。保留现有 `chalab-postgres` 容器、`pgdata` 卷和已有数据库；不要为了名称整齐重命名、重建或清空。
- dude 仍使用 `alfred` 数据库；初始化脚本创建 `makeitspecific` 不代表应用已迁移到该库。
- 当前聊天是 `POST /dude/api/chat/message`，SSE 为节点进度；不是旧文档中的 `/chat/stream?v=2`。
- `make dev` 启动 dude Python、Journal、Go 登录/管理和 Portal 代理，仅监听回环地址；`make stop` 按进程身份停止本次启动器，不按端口杀进程。配置与验证见 [本地联调](docs/local-development.md)。
- 现有用户角色与管理员目录不等于所有 Python API 已完成多用户数据隔离。
- 当前图不执行用户项目代码；旧 `tools/`、`skills/` 和教程不能作为重新启用执行能力的依据。
- dude 主链路为结构化 PostgreSQL 项目资料 + 依赖驱动阶段 + 只读发布版 LLM Wiki。`wiki_tools.cli` 独立管理来源、模型编译、审核发布与回滚；在线不联网更新 Wiki、不初始化向量库。无发布版本时可显式使用人工种子，不能宣称已经 LLM 编译。旧 RAG/记忆代码和数据保留但不启用。详见 [LLM Wiki](dude/docs/llm-wiki.md)。

## 改动边界

- 根目录负责编排、代理、首页、启动器、运维和文档；业务逻辑留在子项目。
- 子项目间不要直接导入代码；各自维护依赖，Python 以 `pyproject.toml` + `uv.lock` 为准，Go 以 `go.mod` + `go.sum` 为准。
- dude 按 00–08 职责逐块修改，只做任务所需的最小联动；产品“只给方案”不限制开发者维护本仓库时编写代码或执行测试。
- 保留与任务无关的未提交/未跟踪文件，尤其 dude 的界面、管理员与用量改动；不要批量恢复文件。
- 不读取或复述真实密钥，不把 `.env`、私钥、数据库导出、用户数据和本地归档写入认知文档或提交。
- 数据库测试先检查测试代码和目标库；不要把生产连接串交给会建表、删表或写测试数据的脚本。
- 按改动运行适当检查；明确区分静态检查、离线替代模型测试、真实模型验证、数据库验证和线上验证。

## 维护认知

改变路由、节点、数据归属、启动方式或模块边界时，同步更新架构说明和相关模块文档。当前行为由代码/配置证明，目标边界由 PRODUCT 定义；两者不一致时记录缺口，不把目标写成已实现。历史记录在 [旧模型文档历史](docs/history/model-context-history.md)，无需默认加载。
