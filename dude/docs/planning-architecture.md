# dude 规划架构：资料、阶段、Wiki 与交付

更新：2026-10-26。本地代码实现说明，不表示已发布。产品依旧只给新项目方案，不写代码或执行用户项目。已补 06 LLM Wiki 管理编译/发布，保留现有前端与管理员功能。

## 一条消息如何处理

1. 从 PostgreSQL 读取当前会话最新项目资料，再组装对话窗口、辅助摘要；客户端维度不能覆盖已保存资料。
2. `knowledge` 根据本轮消息、已有目标/约束读取发布版 Wiki，按关键词和互链组装有来源摘要的上下文包；在线不联网抓取。
3. `planner` 提取目标、范围、流程、验收、要求/假设/待定项；程序计算依赖和可追问字段。
4. 多个未解决项可交给产品与运行两个内部角色并行检查，问题按依赖过滤、去重，最多三个合为一次回复。内部 JSON 不作为额外聊天消息发送。
5. 信息足够后生成一份完整 Markdown，先方向检查，再程序结构检查和模型审核；重试有上限。只有保存成功后才交付成功事件。

公开节点：`router → enrich → knowledge → planner → gap_analysis/clarify 或 execute → checkpoint → reflect`。`execute` 是兼容的文案节点名称，没有执行工具。`rag` 不再注册；旧函数/构造参数仅兼容留存，不会退回向量检索。

## 项目资料是依据

`task_contracts.contract` 既有 JSONB 保存目标、目标用户、范围、流程、验收、约束、明确要求、默认假设、非阻塞待定项。新增字段：

| 字段 | 含义 |
| --- | --- |
| schema_version | JSON 结构版本，当前 1；不是数据库迁移号 |
| workflow | 当前阶段、已具备/可提问/受依赖阻塞的资料、阻塞问题 |
| provenance | 字段最近变化时间，默认或模型提取的来源类型；不将模型提取假装成用户确认 |
| references | Wiki 路径、release/page/source 内容摘要、编译/激活时间、来源出处和时效缺口 |

同会话使用同一个 contract_id，追加版本而非覆盖旧行。未提供的字段沿用上一版，scope 部分更新保留未提及的子字段；明确开始另一项目才 reset。已完成资料的读取失败立即停止；保存失败返回错误，不发布成功方案。模型整理失败保留之前的资料，要求重试，不按旧资料直接交付忽略本轮的新要求。

这是会话内资料持久化，不是跨会话自动恢复项目的产品承诺。旧数据缺少新增字段时按默认解析，无需删表或迁移列。跨用户归属校验尚未完成；同一会话同时发送多条消息的版本竞争也尚未实现专门的并发控制，不应承诺多人协作或同时写同一项目。

## 阶段由依赖决定

目标不清时只澄清目标。有目标后，第一版范围和完整使用流程可以一起问；验收依赖两者。所有核心信息具备但仍有影响范围/权限/费用的矛盾时，先解冲突。资料足够后进入方案生成；通过并保存才标记 delivered。

阶段不是固定问卷，也不限制聊天轮数。模型可从用户已经说过的内容提取多项资料；验收可以依据已明确的功能给出标注为默认的建议。非核心技术走简单默认方案，明确要求始终优先。

## Wiki 的实际含义

采用 nvk/llm-wiki 的来源编译和互链模式，实现独立适配层。上游 compile 是 Agent 流程规范，不能当作可直接调用的编译 API；本项目 `wiki_tools.compiler` 实际调用已有聊天模型综合资料，产生结构化候选，再生成可读 Markdown。完整说明见 [LLM Wiki](llm-wiki.md)。

- `wiki_tools/cli.py`：init、ingest-note、refresh、compile、check、publish、rollback、status 管理入口。
- `wiki_sources/notes/` 与既有 `wiki/*.md`：明确选择的通用技术笔记与人工种子，不是用户记忆。
- `var/wiki-work/`：不可变来源快照和候选；`var/wiki-published/`：已发布版本及原子指针。两者 Git 忽略、单独备份。
- `services/published_wiki.py`：在线只读；旧 `wiki_service.py/index.json/log.md` 仅兼容保留，不再作为当前服务接线。

标题/关键词和一跳关联页决定参考内容，单次搜索最多 8 页，上下文包不超过 18000 字符。先完整校验发布摘要和派生文件，再提供快照；运行中损坏保留上次有效快照并标记 degraded，冷启动可回退 previous。不可恢复时启动失败。搜索/统计需登录；旧 reindex 返回 410，指向管理员编译发布。

维护步骤：筛选来源→快照→模型编译→结构与引用检查→管理员读原文和候选→确认完整摘要发布。编译不能自报人工 verified。首次没有发布且允许种子时为 maintainer-seed，不是假装的 LLM 成果。不要自动导入旧 knowledge_base、用户聊天或用户方案。

## 时效事实与联网边界

`OFFICIAL_REFERENCE_ENABLED` 已停用。官方页面只在管理员显式 refresh 时读取，仅支持 Python、PostgreSQL、Django 三个固定页面，不接受任意 URL；成功后仍需重新编译、审阅、发布才影响对话。

管理员抓取验证 TLS、不跟随重定向、不读环境代理；总时限 15 秒，解压后上限 256 KB，只接收 HTML/文本，提取文本最多 64 KB，超限失败，不悄悄截断。更新新增快照，失败保留之前来源。

来源抓取、编译和发布日期均不证明事实今天仍有效。在线不实时核实；命中中英文版本/价格/配额等时效词时标记 unverified，禁止无证据断言。当前白名单不覆盖商业价格，这不是通用搜索或事实验证器。

## 配置、兼容与更新

主存储与用量服务统一优先 `DB_HOST/DB_PORT/DB_NAME/DB_USER`，回退旧 `PG_HOST/PG_PORT/PG_DATABASE/PG_USER`，密码继续使用 `PGSQLPASSWORD`。子 Compose 保持共享 postgres 与 alfred 库；不改数据库名、用户已有数据或卷。

OpenAI 兼容聊天和 Wiki 编译复用聊天凭证、端点和模型，不强制嵌入凭证。Compose 透传对应模型配置，只读挂载发布目录及 DUDE_WIKI_ALLOW_SEED 开关；旧 MEMORY_ENABLED 不启用向量记忆。旧 RAG 源码、依赖、知识目录和向量表保留，不自动删除或写入。

应用配置就绪后的更新操作从 Portal 根目录执行：

```bash
docker compose config --quiet
docker compose up -d --build dude-api
docker compose ps dude-api
docker compose exec -T dude-api curl -fsS http://localhost:8000/api/health
```

本轮不引入新必填密钥。Git 拉取不包含来源快照或发布产物，须按 [LLM Wiki 部署步骤](llm-wiki.md) 在服务器编译发布或传输完整候选。发布后建议手动设置 DUDE_WIKI_ALLOW_SEED=false。不要为此次变更重建 PostgreSQL 卷或运行迁移。

## 验证与尚未验收的部分

从 dude 运行离线测试：

```bash
uv run --frozen python -m pytest tests/test_graph.py tests/test_planning.py tests/test_planning_flow.py tests/test_usage_identity.py tests/test_project_state.py tests/test_wiki_service.py tests/test_llm_wiki.py tests/test_planning_startup.py -q
```

覆盖依赖、局部更新/重置、来源、SSE、模型/保存失败、Wiki 越界、官方超时/重定向/超大响应、无需向量服务的启动、健康状态及环境兼容。HTTP 与模型使用离线替身，不调用真实 key。

数据库集成测试仅接受显式 `DUDE_PLANNING_TEST_DATABASE_URL`，数据库名须以 `alfred_planning_test` 开头。准备独立临时实例/测试库后运行：

```bash
uv run --frozen python -m pytest tests/test_planning_postgres.py -q
```

此前规划架构整改已在独立 socket、无 TCP 监听的临时 PostgreSQL 16 实例验证同会话保存、版本、重新连接、旧 JSON 兼容，未安装 vector 扩展，结束后已停实例。2026-10-26 的 Wiki 改动不写数据库，未重跑该数据库集成测试；不要将旧 `test_session_store.py` 直接指向业务库。

真实模型的中文沟通质量、官方页面真实联网、浏览器全流程、服务器容器部署尚未验收。当前环境无 Docker/nginx，未执行 Compose 和 nginx 运行检查。规则检查不能保证语义正确；多用户数据隔离仍是既有缺口。后续 08 已补齐开发认证代理和 SSE，验证范围见 [本地联调](../../docs/local-development.md)。
