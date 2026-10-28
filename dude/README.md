# dude — 面向新手的 Vibe Coding 方案助手

把「我有个想法」聊成一份能直接交给 Codex 等编程 Agent 开始实施的项目方案。

dude 面向没有开发经验、不了解技术名词的人。它负责拆解想法、解释选择，最终交付给编程 Agent 的技术方案和一份只到启动、体验 Demo 的操作手册。代码编写、实际排错和部署由用户及编程 Agent 完成。

## 产品方向与当前状态

2026-10-28：目标架构已确认，见 [架构基线](docs/dude-architecture-baseline.md)。独立 [dude-orchestrator](dude-orchestrator/README.md) 已实现 TypeScript 服务、认证项目 API、Brief 草稿/版本与成对文档持久层。Pi、Wiki 在线适配、React 和网页切流尚未接入；`make dev` 与线上仍运行原 Python 链路。下文旧实现状态不代表新的两份文档交付已经上线。

当前已完成第一轮对话链路调整：统一新项目规划入口、通俗提问、非核心技术默认兜底、明确要求与假设分别保存，以及整篇方案校验。方案生成节点只返回文案，不绑定旧执行工具。

2026-10-26：主链路为 PostgreSQL 结构化项目资料、依赖驱动的轻量阶段、内部并行检查和只读发布版 LLM Wiki。管理员独立执行来源快照→模型编译→检查→明确发布；在线不联网更新知识，也不启动向量索引、嵌入或跨会话向量记忆。没有发布时可使用明确标记的人工种子。旧源码与数据库保留；操作、部署及 Git 忽略目录的备份见 [LLM Wiki](docs/llm-wiki.md)，规划见 [架构](docs/planning-architecture.md)。

现有工程仍包含旧技能、工具、记忆和交接卡代码；聊天与登录已改为浅色界面，支持单条回复复制/下载，独立最终方案导出与版本管理仍未完成。这些历史实现不代表首版产品承诺。当前验证以离线模型回归为主，真实模型的中文沟通与方案质量仍需实际试聊。

- [产品定义](PRODUCT.md)：产品范围、沟通规则、默认兜底和最终交付标准，以此为准。
- [逐步优化路线](docs/product-roadmap.md)：后续分阶段调整及验收要求。
- [板块划分](docs/product-modules.md)：9 个职责板块（00–08）、文件边界和逐块修改顺序；后续以板块编号指定任务。
- [开发说明](CLAUDE.md)：现有实现与开发约束。
- 旧能力规范和任务契约教程保留作历史及技术参考，发生冲突时以产品定义为准。

## 用户怎样使用

1. 描述一个新项目的想法，例如「我想做一个记录自己读过的书的网站」。
2. dude 用生活场景拆解：谁使用、进来做什么、数据怎么保存、第一版做到哪里。
3. 遇到技术选择时，先讲对体验、成本和维护的影响，再推荐方案。用户不懂或没有偏好时采用最简单的小规模方案。
4. 核心信息足够后，生成一份完整方案。默认假设与用户明确确认的要求分别标注。
5. 用户把文案交给编程 Agent，由其按阶段实施和验证。

不要求用户先选框架、数据库或架构，也不为了凑满问卷反复追问。若想法互相矛盾或范围过大，dude 说明影响并建议取舍；改变核心范围需用户确认。

## 首版边界

| 项目 | 首版约定 |
| --- | --- |
| 支持对象 | 从零开始的新项目 |
| 输出 | 一份用户看得懂、编程 Agent 可以执行的方案文案 |
| 信息不足 | 非关键细节使用已标注的简单默认方案；核心目标有歧义时继续澄清 |
| 技术方案 | 用案例解释优缺点，给推荐与适用边界 |
| 部署、安全、备份、成本 | 属于方案内容，按项目实际需要说明 |
| 编码和执行 | 不输出代码、伪代码、SQL 或可执行配置，不改项目、不执行命令、不部署 |
| 实际报错 | 不接手排错；可以给出交由编程 Agent 处理错误的流程方案 |
| 已有项目改造 | 后续建立专门流程，首版不支持 |
| 后续修改方案 | 待调研，尚未决定采用项目记忆还是用户提供上次方案 |

默认小规模不意味着删掉核心功能，也不意味着忽略安全、权限或数据持久化。用户已明确的要求优先于默认值。

## 最终方案包含什么

按项目需要组织以下内容，保持为一个自包含文档：

- 项目目标、目标用户和实际使用场景。
- 第一版范围、暂不做的内容、主要页面和完整操作流程。
- 推荐技术与理由，以及为什么适合当前规模。
- 数据保存、权限规则和关键业务约束。
- 分阶段实施任务、依赖关系、每阶段验证方法。
- 部署方式、安全与备份要求、成本假设及可能的额外费用。
- 可观察、可验证的验收标准与报错处理流程。
- 已确认要求、默认假设、仍需决定的问题。

方案应能脱离聊天记录使用，不能要求编程 Agent 猜测「照刚才说的做」。具体交付标准见 [PRODUCT.md](PRODUCT.md)。

## 当前工程与本地开发

**统一开发入口在 Portal 根目录，不在本目录。** 源码目录已从 `MakeItSpecific/` 更名为 `dude/`；旧服务器升级先看 [更名迁移](../docs/dude-rename.md)。

```bash
cd /home/yoiwerr/portal
make dev
```

当前入口为 `http://localhost:8080/dude/`，`make dev` 已启动并代理 dude-admin（8083），登录入口为 `/dude/auth/`。配置与验证见 [本地联调](../docs/local-development.md)。之前的 `8767` 是历史临时预览端口，不是标准开发入口。

dude 位于 Portal 的 `dude/`，Python 服务名为 `dude-api`，容器名为 `dude-api`；[dude-admin](dude-admin/README.md) 提供账号认证和管理。根级 Compose 负责 PostgreSQL、nginx 及各项目编排。子目录 Compose 不包含独立 PostgreSQL 服务。

当前规划运行依赖：Python 3.12+、uv、PostgreSQL、所选聊天模型的凭证。Portal 可以继续复用现有 pgvector 镜像，但规划主链路不要求 vector 扩展，也不需要 DashScope 嵌入或重排凭证。旧依赖保留兼容，未在本轮批量升级或删除。

只有单独安装或调试 dude Python 后端时才需要进入本目录，以下命令不会启动整个 Portal：

```bash
cd /home/yoiwerr/portal/dude
uv sync --frozen
```

先检查已有环境配置，保留原文件和真实密钥。配置模板见根级及子项目的 `.env.example`，生产运维参考 [Portal 运维说明](../CONTROLWEB.md)。不要把模板里的示例值当作生产密码。

当前 Python 配置优先读取 Portal 根级 `.env`，根级不存在时才读取子项目 `.env`。直接本地运行主要需要：

| 变量 | 用途 |
| --- | --- |
| `DB_HOST`、`DB_PORT` | 本地进程可访问的 PostgreSQL 地址和端口；回退 `PG_HOST/PG_PORT` |
| `DB_NAME`、`DB_USER`、`PGSQLPASSWORD` | 库、用户、密码；库/用户回退 `PG_DATABASE/PG_USER`，现有部署保持 `alfred` |
| `JWT_SECRET` | Python 与 dude-admin 共用的签名密钥，至少 32 字符 |
| `LLM_PROVIDER` 及对应 API Key | 聊天模型提供方与凭证 |
| `OPENAI_BASE_URL`、`OPENAI_MODEL` | 使用 OpenAI 兼容服务时指定端点和模型；Compose 已透传 |
| `DUDE_WIKI_ALLOW_SEED` | 默认 true；没有发布时允许人工种子。发布后建议设 false |
| `DUDE_WIKI_PUBLISHED_DIR` | 本地覆盖只读发布目录；Compose 固定容器路径。旧 OFFICIAL_REFERENCE_ENABLED 已停用 |

本地直跑和 Compose 的变量映射并不完全相同，以 [config.py](config.py) 和 [docker-compose.yml](docker-compose.yml) 为准。已有数据库不因文档更新而重命名；数据库端口仅在本机开发确有需要时限制到回环地址。

Python 主存储与用量配置现统一优先使用 `DB_*`，兼容旧 `PG_*`。不要将两套变量指向不同数据库；Compose 仍固定连接共享 postgres 服务的 alfred 库，已有数据库和卷不变。

数据库和配置就绪后，在 `dude/` 运行：

```bash
uv run --frozen python app.py
```

Python 开发服务默认 `http://localhost:8001`，API 文档为 `/docs`，健康检查为 `/api/health`。根级 `make dev` 已启动 dude-admin 并提供 `/dude/auth/`、`/dude/admin/` 和 `/dude/api/v1/auth|admin/*` 的分流，同时兼容旧认证 API；须先配置共享数据库和 JWT 密钥。

管理员登录后可查看用户资料、角色、状态及近 30 天已记录用量；普通用户无管理接口权限。当前不支持修改角色、封号或计费，用量不等于账单。账号初始化与统计口径见 [dude-admin README](dude-admin/README.md#管理员与普通用户)。

启动时看到进程运行不等于初始化完成：`/api/health` 返回 200 才表示数据库和 Agent 就绪，返回 503 表示服务尚不可用。模型服务可能产生费用，按配置及实际调用量评估。

生产部署从 Portal 根目录操作，先完成根级配置检查及数据库初始化，再构建启动相关服务。不要在子项目里假定 `docker compose up` 会建立完整环境。

## 当前实现参考

现有主链路为浏览器 → FastAPI/SSE → LangGraph：读取已保存的项目资料 → 固定规划入口 → 已发布 Wiki 与来源摘要 → 需求与依赖判断 → 一批追问或完整文案 → 方向和质量检查 → 保存再交付。范围与操作流程可以并行澄清，验收依赖它们；用户只看到合并后的问题。PostgreSQL 保存会话与 JSONB 资料版本，前端仍为原生 HTML/CSS/JavaScript。

| 目录 | 当前作用 |
| --- | --- |
| `core/`、`prompts/` | Agent 编排与提示词 |
| `routers/` | 对话、会话、导出、反馈、Wiki API |
| `services/`、`models/` | 存储、检索和数据模型 |
| `skills/`、`tools/`、`memory/` | 旧工作流技能、工具及记忆机制，后续按产品边界审查 |
| `static/` | 当前工作台前端 |
| `wiki/` | 既有人工种子笔记，非当前发布目录 |
| `wiki_tools/`、`wiki_sources/` | 管理员编译/发布工具、通用技术笔记 |
| `var/wiki-work/`、`var/wiki-published/` | Git 忽略的原文/候选及发布产物，须单独备份 |
| `knowledge_base/` | 历史 RAG 资料，保留但不自动索引或迁入 Wiki |
| `tests/` | 现有测试 |
| `dude-admin/` | Go 认证与管理服务 |

以下是当前内部 API 路径，Portal 对外使用 `/dude/` 前缀，鉴权接口由 nginx 路由到 dude-admin：

| 方法 | 路径 | 当前用途 |
| --- | --- | --- |
| `GET` | `/api/health` | 就绪检查 |
| `POST` | `/api/chat/message` | 节点级 SSE 对话 |
| `GET` | `/api/sessions` | 会话列表 |
| `GET` / `DELETE` | `/api/sessions/{id}` | 会话详情、删除 |
| `GET` | `/api/sessions/{id}/export` | Markdown 导出 |
| `POST` | `/api/sessions/import` | 导入旧交接资料 |
| `GET` | `/api/chat/{id}/contract` | 读取需求资料 |
| `POST` | `/api/chat/{id}/contract/confirm`、`update` | 确认/修改需求资料 |
| `POST` | `/api/feedback` | 反馈 |
| `GET` | `/api/feedback/stats` | 反馈统计 |
| `GET` | `/api/knowledge/search`、`/api/knowledge/stats` | 知识检索、统计 |
| `POST` | `/api/knowledge/reindex` | 已停用，登录后返回 410；Wiki 随 Git 部署 |
| `GET` / `POST` | `/api/files/download` / `/api/files/save` | 导出文件下载 / Markdown 保存 |

当前对话生成完整方案后会先做章节、占位内容和明显代码/命令的程序检查，再审核整篇内容；失败最多修正两次，仍失败就返回错误，不标记方案完成。程序检查只能发现部分结构问题，不能保证建议的语义或事实正确。

当前可复制或下载单条回复为 Markdown；服务端会话导出接口仍输出完整聊天记录，没有独立最终方案导出/版本库。旧交接资料仅保留导入接口，当前页面已移除入口。

注意：账号登录与管理员角色功能不代表 Python 资源接口已完成用户隔离。会话详情、删除和导出当前缺少鉴权，会话列表和契约未按用户归属校验；完整现状见 [项目认知](../docs/project-context.md)。

## 开发验证

先按 [验证范围与副作用](../docs/project-context.md) 选择测试。`test_session_store.py` 会按当前配置连接真实数据库并写入数据；不要直接把全部测试指向已有业务库。

离线规划验证不需要在线模型或数据库：

```bash
uv run --frozen python -m pytest tests/test_graph.py tests/test_planning.py tests/test_planning_flow.py tests/test_usage_identity.py tests/test_project_state.py tests/test_wiki_service.py tests/test_planning_startup.py -q
```

这些测试使用确定性的替代模型，检查真实图分支、默认来源保存、SSE 成功/失败状态和同会话契约版本。00 的离线验证还覆盖四种回复模式的实际节点序列、联合重试上限、参考资料传递和 SSE 兼容。后续按 [板块划分](docs/product-modules.md) 一次只推进一块。
