# Alfred — 面向新手的 Vibe Coding 方案助手

把「我有个想法」聊成一份能直接交给 Codex 等编程 Agent 开始实施的项目方案。

Alfred 面向没有开发经验、不了解技术名词的人。它负责拆解想法、解释选择、明确范围和验收方式，最终交付一份独立的方案文案。代码编写、实际排错和部署由用户及编程 Agent 完成。

## 产品方向与当前状态

当前已完成第一轮对话链路调整：统一新项目规划入口、通俗提问、非核心技术默认兜底、明确要求与假设分别保存，以及整篇方案校验。方案生成节点只返回文案，不绑定旧执行工具。

现有工程仍包含旧技能、工具、记忆和交接卡代码，界面与导出尚未全部对齐；这些历史实现不代表首版产品承诺。当前验证以离线模型回归为主，真实模型的中文沟通与方案质量仍需实际试聊。

- [产品定义](PRODUCT.md)：产品范围、沟通规则、默认兜底和最终交付标准，以此为准。
- [逐步优化路线](docs/product-roadmap.md)：后续分阶段调整及验收要求。
- [板块划分](docs/product-modules.md)：9 个职责板块（00–08）、文件边界和逐块修改顺序；后续以板块编号指定任务。
- [开发说明](CLAUDE.md)：现有实现与开发约束。
- 旧能力规范和任务契约教程保留作历史及技术参考，发生冲突时以产品定义为准。

## 用户怎样使用

1. 描述一个新项目的想法，例如「我想做一个记录自己读过的书的网站」。
2. Alfred 用生活场景拆解：谁使用、进来做什么、数据怎么保存、第一版做到哪里。
3. 遇到技术选择时，先讲对体验、成本和维护的影响，再推荐方案。用户不懂或没有偏好时采用最简单的小规模方案。
4. 核心信息足够后，生成一份完整方案。默认假设与用户明确确认的要求分别标注。
5. 用户把文案交给编程 Agent，由其按阶段实施和验证。

不要求用户先选框架、数据库或架构，也不为了凑满问卷反复追问。若想法互相矛盾或范围过大，Alfred 说明影响并建议取舍；改变核心范围需用户确认。

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

Alfred 位于 Portal 的 `MakeItSpecific/`，Python 服务名为 `specific-api`，容器名为 `alfred-api`；[AlfredAdmin](AlfredAdmin/README.md) 提供账号认证和管理。根级 Compose 负责 PostgreSQL、nginx 及各项目编排。子目录 Compose 不包含独立 PostgreSQL 服务。

当前依赖：Python 3.12+、uv、PostgreSQL + pgvector、模型服务密钥。当前检索链路还使用 DashScope 的嵌入及重排服务，不能只配置聊天模型就假定全部功能可用。

从已有 Portal 仓库安装 Python 依赖：

```bash
cd /home/yoiwerr/portal/MakeItSpecific
uv sync --frozen
```

先检查已有环境配置，保留原文件和真实密钥。配置模板见根级及子项目的 `.env.example`，生产运维参考 [Portal 运维说明](../CONTROLWEB.md)。不要把模板里的示例值当作生产密码。

当前 Python 配置优先读取 Portal 根级 `.env`，根级不存在时才读取子项目 `.env`。直接本地运行主要需要：

| 变量 | 用途 |
| --- | --- |
| `PG_HOST`、`PG_PORT` | 本地进程可访问的 PostgreSQL 地址和端口 |
| `PG_DATABASE`、`PG_USER`、`PGSQLPASSWORD` | 数据库名称、用户和密码；现有部署兼容使用 `alfred` 库 |
| `JWT_SECRET` | Python 与 AlfredAdmin 共用的签名密钥，至少 32 字符 |
| `LLM_PROVIDER` 及对应 API Key | 聊天模型提供方与凭证 |
| `DASHSCOPE_API_KEY` | 当前嵌入及重排所需凭证 |

本地直跑和 Compose 的变量映射并不完全相同，以 [config.py](config.py) 和 [docker-compose.yml](docker-compose.yml) 为准。已有数据库不因文档更新而重命名；数据库端口仅在本机开发确有需要时限制到回环地址。

当前检查发现子项目 Compose 使用 `DB_HOST`、`DB_PORT`、`DB_NAME`，而 Python 配置读取 `PG_HOST`、`PG_PORT`、`PG_DATABASE`，存在映射不一致。本轮不修改运行配置；后续部署前需单独对齐并验证数据库就绪，不能假定上述变量等价。

数据库和配置就绪后，在 `MakeItSpecific/` 运行：

```bash
uv run --frozen python app.py
```

Python 开发服务默认 `http://localhost:8001`，API 文档为 `/docs`，健康检查为 `/api/health`。完整登录流程还需要 AlfredAdmin 和共享密钥；Portal 开发路由使用 `/alfred/`，通用启动器从 Portal 根目录通过 `make dev` 使用。

启动时看到进程运行不等于初始化完成：`/api/health` 返回 200 才表示数据库和 Agent 就绪，返回 503 表示服务尚不可用。模型服务可能产生费用，按配置及实际调用量评估。

生产部署从 Portal 根目录操作，先完成根级配置检查及数据库初始化，再构建启动相关服务。不要在子项目里假定 `docker compose up` 会建立完整环境。

## 当前实现参考

现有主链路为浏览器 → FastAPI/SSE → LangGraph：固定规划入口 → 检索问题准备 → 知识检索 → 需求规划，随后选择追问或文案生成；文案经过方向与质量检查，有限重试后返回结果或错误。00 首轮已移除图内空工程检查节点及不可达多 Agent 分支，方案生成不调用执行工具。PostgreSQL/pgvector 保存会话、契约与检索数据。前端使用原生 HTML/CSS/JavaScript。

| 目录 | 当前作用 |
| --- | --- |
| `core/`、`prompts/` | Agent 编排与提示词 |
| `routers/` | 对话、会话、导出、反馈及上传 API |
| `services/`、`models/` | 存储、检索和数据模型 |
| `skills/`、`tools/`、`memory/` | 旧工作流技能、工具及记忆机制，后续按产品边界审查 |
| `static/` | 当前工作台前端 |
| `knowledge_base/` | 检索参考资料 |
| `tests/` | 现有测试 |
| `AlfredAdmin/` | Go 认证与管理服务 |

以下是当前内部 API 路径，Portal 对外使用 `/alfred/` 前缀，鉴权接口由 nginx 路由到 AlfredAdmin：

| 方法 | 路径 | 当前用途 |
| --- | --- | --- |
| `GET` | `/api/health` | 就绪检查 |
| `POST` | `/api/chat/stream?v=2` | SSE 对话 |
| `GET` | `/api/sessions` | 会话列表 |
| `GET` / `DELETE` | `/api/sessions/{id}` | 会话详情、删除 |
| `GET` | `/api/sessions/{id}/export` | Markdown 导出 |
| `POST` | `/api/sessions/{id}/handover` | 旧交接卡生成 |
| `POST` | `/api/feedback` | 反馈 |
| `GET` | `/api/feedback/stats` | 反馈统计 |
| `POST` | `/api/knowledge/upload`、`/api/files/upload` | 知识文件、附件上传 |

当前对话生成完整方案后会先做章节、占位内容和明显代码/命令的程序检查，再审核整篇内容；失败最多修正两次，仍失败就返回错误，不标记方案完成。程序检查只能发现部分结构问题，不能保证建议的语义或事实正确。

目前可从对话复制方案。现有导出接口仍导出聊天记录，交接卡也保持旧行为；直接导出单份方案和界面简化留到下一轮。

## 开发验证

在依赖及必要环境就绪后运行现有测试：

```bash
uv run --frozen python -m pytest tests/ -v
```

离线规划验证不需要在线模型或数据库：

```bash
uv run --frozen python -m pytest tests/test_graph.py tests/test_planning.py tests/test_planning_flow.py -q
```

这些测试使用确定性的替代模型，检查真实图分支、默认来源保存、SSE 成功/失败状态和同会话契约版本。00 的离线验证还覆盖四种回复模式的实际节点序列、联合重试上限、参考资料传递和 SSE 兼容。后续按 [板块划分](docs/product-modules.md) 一次只推进一块。
