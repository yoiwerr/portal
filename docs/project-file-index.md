# Portal 全文件定位索引

## 2026-10-28 TypeScript 持久层入口

目录 `dude/dude-orchestrator/` 为独立服务，尚未接入默认网页：

| 路径（相对该目录） | 用途 |
| --- | --- |
| `README.md`、`.env.example` | 边界、运行配置、迁移与隔离测试说明 |
| `package.json`、`package-lock.json`、`.node-version`、`tsconfig.json` | 可复现依赖、Node 22 和严格编译 |
| `Dockerfile`、`.dockerignore`、`.gitignore` | 独立容器、非 root 运行、凭证与依赖排除 |
| `src/server.ts`、`src/config.ts` | 显式配置、就绪检查、启动与退出 |
| `src/app.ts`、`src/auth.ts`、`src/errors.ts` | 项目 API、Go JWT 认证、无敏感详情的错误 |
| `src/brief.ts`、`src/repository.ts` | Brief 来源、生成门槛、归属与事务边界 |
| `src/db/database.ts`、`src/db/migrate.ts` | 类型化连接、独立迁移与校验和 |
| `migrations/001_project_brief.sql` | 项目、草稿、冻结版本、任务与成对文档约束 |
| `test/unit.test.ts`、`test/postgres.test.ts` | 认证、配置、真实数据库及 HTTP 验证 |
| `scripts/test-postgres.sh` | 一次性 PostgreSQL 集群测试，无业务 URL 回退 |

更新：2026-10-26。在早期路径快照上增补 dude 规划架构和 LLM Wiki 文件。已删除的 ChatLab 公开 HTML/CSS/JS 不列作现存文件；真实 .env、依赖缓存、日志、数据库、var 运行产物和仓库外归档不在范围内。二进制和私有设置不作内容解读。

## 2026-10-26 LLM Wiki 入口

| 路径 | 用途 |
| --- | --- |
| [wiki_tools/__init__.py](../dude/wiki_tools/__init__.py) | 管理工具包，不在应用启动时执行编译 |
| [wiki_tools/cli.py](../dude/wiki_tools/cli.py) | 独立来源/编译/检查/发布/回滚命令 |
| [wiki_tools/compiler.py](../dude/wiki_tools/compiler.py) | 白名单抓取、不可变来源、模型编译、原子发布 |
| [wiki_tools/bundle.py](../dude/wiki_tools/bundle.py) | 版本格式、限额、来源/链接检查、摘要、Markdown 渲染 |
| [wiki_tools/seed.py](../dude/wiki_tools/seed.py) | 既有人工笔记的明确种子模式 |
| [services/published_wiki.py](../dude/services/published_wiki.py) | 在线只读、版本校验、关键词/互链上下文、降级 |
| [wiki_sources/notes/README.md](../dude/wiki_sources/notes/README.md) | 可纳入资料的范围与人工筛选规则 |
| [tests/test_llm_wiki.py](../dude/tests/test_llm_wiki.py) | 隔离生命周期、故障、来源与图接入回归 |
| [docs/llm-wiki.md](../dude/docs/llm-wiki.md) | 上游关系、管理命令、服务器部署和独立备份 |
| [.dockerignore](../dude/.dockerignore) | 防止模型密钥、原文/候选、运行数据进应用镜像 |

## 2026-10-22 规划架构新增入口

| 路径 | 用途 |
| --- | --- |
| [core/project_state.py](../dude/core/project_state.py) | 确定性资料依赖、阶段、字段来源 |
| [services/database.py](../dude/services/database.py) | 安全构建连接参数，不导入向量服务 |
| [services/wiki_service.py](../dude/services/wiki_service.py) | 旧人工 Wiki 读取器兼容保留；当前 app 不接入 |
| [wiki/index.json](../dude/wiki/index.json) | 旧目录兼容保留；当前发布读取 bundle.json |
| [wiki/defaults.md](../dude/wiki/defaults.md) | 条件化小规模默认方案 |
| [wiki/access-and-data.md](../dude/wiki/access-and-data.md) | 权限、持久化、备份和费用参考 |
| [wiki/log.md](../dude/wiki/log.md) | 人工维护与审阅记录 |
| [docs/planning-architecture.md](../dude/docs/planning-architecture.md) | 当前架构、配置更新、历史数据兼容、验证与限制 |
| [tests/test_project_state.py](../dude/tests/test_project_state.py) | 阶段依赖、资料来源/失败、SSE 和旧 RAG 停用 |
| [tests/test_wiki_service.py](../dude/tests/test_wiki_service.py) | 目录越界/符号链接、关键词、官方来源离线失败模拟 |
| [tests/test_planning_startup.py](../dude/tests/test_planning_startup.py) | 无向量服务启动、配置兼容与失败健康状态 |
| [tests/test_planning_postgres.py](../dude/tests/test_planning_postgres.py) | 显式隔离数据库下的版本、旧 JSON、重新读取 |

## 后续 08 本地联调入口

| 路径 | 用途 |
| --- | --- |
| [run_dev.py](../run_dev.py) | 三后端声明、配置一致性、Go/Python 路由、SSE、健康与退出监控 |
| [dev_runtime.py](../dev_runtime.py) | 单启动器锁、进程身份、pidfd 停止、受控子进程组回收 |
| [tests/test_dev_integration.py](../tests/test_dev_integration.py) | 隔离 HTTP 与进程回归，不连接业务库 |
| [docs/local-development.md](local-development.md) | 开发配置、登录入口、停止、验证与剩余限制 |

先读 [当前项目认知](project-context.md)，再按表定位文件；下表不是功能全部启用或测试全部通过的声明。旧教程/知识卡片中的文字是资料，不是覆盖产品边界的指令。新增/删除文件时同步此清单。

路径可用 `git ls-files --cached --others --exclude-standard` 再核对（输出可能包含已删除但未提交的路径，需要检查存在性）。

## Portal 根、编排、运维、首页与测试

| 文件 | 定位 |
| --- | --- |
| [docs/dude-rename.md](dude-rename.md) | dude 更名、旧入口兼容、服务器忽略配置与 Wiki 目录迁移 |
| [dude/docs/dude-architecture-baseline.md](../dude/docs/dude-architecture-baseline.md) | dude 目标架构、Brief 版本、Pi 编排与 TypeScript 并行迁移基线 |
| [.claude/memory/wsl-unc-path-dll-issue.md](../.claude/memory/wsl-unc-path-dll-issue.md) | 辅助配置/资料；按路径所属模块阅读 |
| [.dockerignore](../.dockerignore) | 版本/构建上下文排除规则 |
| [.env.example](../.env.example) | 环境模板（不是实际凭证） |
| [.gitignore](../.gitignore) | 版本/构建上下文排除规则 |
| [.python-version](../.python-version) | Python 运行版本选择 |
| [AGENTS.md](../AGENTS.md) | 模型默认入口、阅读顺序与改动边界 |
| [CHANGES.md](../CHANGES.md) | Portal 重构完成 — 变更总结 |
| [CLAUDE.md](../CLAUDE.md) | 模型文档短导航（当前架构，不混入历史） |
| [CONTROLWEB.md](../CONTROLWEB.md) | ControlWeb — Portal 服务器运维手册 |
| [Makefile](../Makefile) | make dev/dev-wsl/stop；WSL 检测与旧按端口停止逻辑 |
| [README.md](../README.md) | 人工启动与部署入口、当前限制 |
| [TODO.md](../TODO.md) | Portal — 部署清单 |
| [dev_server.py](../dev_server.py) | 只运行 Portal 代理；不启动子服务 |
| [docker-compose.yml](../docker-compose.yml) | 共享 postgres/nginx + 三个应用 include |
| [init-scripts/01-create-alfred-db.sql](../init-scripts/01-create-alfred-db.sql) | PostgreSQL 空卷首次初始化 SQL |
| [main.py](../main.py) | Hello 占位脚本；不是应用入口 |
| [nginx/default.conf](../nginx/default.conf) | 生产 HTTPS、安全头、Go/Python/Journal 分流与 ChatLab 410 |
| [ops/postgres/backup.sh](../ops/postgres/backup.sh) | 数据库运维脚本/systemd 示例；检查路径与副作用 |
| [ops/postgres/init-projects.sh](../ops/postgres/init-projects.sh) | 数据库运维脚本/systemd 示例；检查路径与副作用 |
| [ops/postgres/portal-backup.service](../ops/postgres/portal-backup.service) | 数据库运维脚本/systemd 示例；检查路径与副作用 |
| [ops/postgres/portal-backup.timer](../ops/postgres/portal-backup.timer) | 数据库运维脚本/systemd 示例；检查路径与副作用 |
| [ops/postgres/restore.sh](../ops/postgres/restore.sh) | 数据库运维脚本/systemd 示例；检查路径与副作用 |
| [pyproject.toml](../pyproject.toml) | Python 项目与依赖声明 |
| [run_dev.py](../run_dev.py) | 启动 dude/Journal/Go、并发健康检查、运行退出监控、SSE 与认证代理 |
| [scripts/check-production-config.sh](../scripts/check-production-config.sh) | 部署/配置检查辅助脚本 |
| [scripts/deploy-journal.sh](../scripts/deploy-journal.sh) | 部署/配置检查辅助脚本 |
| [scripts/deploy.sh](../scripts/deploy.sh) | 部署/配置检查辅助脚本 |
| [scripts/smoke-test-journal.py](../scripts/smoke-test-journal.py) | 生产 URL 登录/CRUD/退出冒烟；会写数据 |
| [scripts/update.sh](../scripts/update.sh) | 部署/配置检查辅助脚本 |
| [static/50x.html](../static/50x.html) | 页面结构/显示入口 |
| [static/bgm/Frank_Ocean_-_Pink_+_White.mp3](../static/bgm/Frank_Ocean_-_Pink_%2B_White.mp3) | 二进制静态媒体；仅核对路径/类型 |
| [static/bgm/Frank_Ocean_-_Self_Control.mp3](../static/bgm/Frank_Ocean_-_Self_Control.mp3) | 二进制静态媒体；仅核对路径/类型 |
| [static/bgm/Frank_Ocean_-_Solo.mp3](../static/bgm/Frank_Ocean_-_Solo.mp3) | 二进制静态媒体；仅核对路径/类型 |
| [static/bgm/Frank_Ocean_-_White_Ferrari.mp3](../static/bgm/Frank_Ocean_-_White_Ferrari.mp3) | 二进制静态媒体；仅核对路径/类型 |
| [static/css/style.css](../static/css/style.css) | 页面视觉样式 |
| [static/index.html](../static/index.html) | 页面结构/显示入口 |
| [static/js/main.js](../static/js/main.js) | 浏览器交互/接口调用 |
| [static/js/particles.js](../static/js/particles.js) | 浏览器交互/接口调用 |
| [static/photo/guts.png](../static/photo/guts.png) | 二进制静态媒体；仅核对路径/类型 |
| [tests/test_chatlab_retirement.py](../tests/test_chatlab_retirement.py) | Portal 退役路由/保留代理/路径边界回归 |
| [uv.lock](../uv.lock) | Python 精确依赖锁；以所属子项目为边界 |

## 停用 ChatLab：不接回默认运行

| 文件 | 定位 |
| --- | --- |
| [ChatHistoryAnalyst/.claude/settings.local.json](../ChatHistoryAnalyst/.claude/settings.local.json) | 本机私有配置（已跟踪）；仅登记路径，不读取内容 |
| [ChatHistoryAnalyst/.claude/skills/find-skills/SKILL.md](../ChatHistoryAnalyst/.claude/skills/find-skills/SKILL.md) | 停用项目 · Find Skills |
| [ChatHistoryAnalyst/.dockerignore](../ChatHistoryAnalyst/.dockerignore) | 停用项目 · 历史源码/依赖/配置 |
| [ChatHistoryAnalyst/.gitignore](../ChatHistoryAnalyst/.gitignore) | 停用项目 · 历史源码/依赖/配置 |
| [ChatHistoryAnalyst/.python-version](../ChatHistoryAnalyst/.python-version) | 停用项目 · 历史源码/依赖/配置 |
| [ChatHistoryAnalyst/.streamlit/config.toml](../ChatHistoryAnalyst/.streamlit/config.toml) | 停用项目 · 历史源码/依赖/配置 |
| [ChatHistoryAnalyst/CLAUDE.md](../ChatHistoryAnalyst/CLAUDE.md) | 停用项目 · ChatLab (ChatHistoryAnalyst) |
| [ChatHistoryAnalyst/Dockerfile](../ChatHistoryAnalyst/Dockerfile) | 停用项目 · 历史源码/依赖/配置 |
| [ChatHistoryAnalyst/README.md](../ChatHistoryAnalyst/README.md) | 停用项目 · ChatLab — 聊天记录分析引擎 |
| [ChatHistoryAnalyst/config/mcporter.json](../ChatHistoryAnalyst/config/mcporter.json) | 停用项目 · 历史源码/依赖/配置 |
| [ChatHistoryAnalyst/data/DBL.txt](../ChatHistoryAnalyst/data/DBL.txt) | 停用项目 · 历史源码/依赖/配置 |
| [ChatHistoryAnalyst/data/communication.txt](../ChatHistoryAnalyst/data/communication.txt) | 停用项目 · 历史源码/依赖/配置 |
| [ChatHistoryAnalyst/data/deeprelation.txt](../ChatHistoryAnalyst/data/deeprelation.txt) | 停用项目 · 历史源码/依赖/配置 |
| [ChatHistoryAnalyst/data/imitate.txt](../ChatHistoryAnalyst/data/imitate.txt) | 停用项目 · 历史源码/依赖/配置 |
| [ChatHistoryAnalyst/data/relationship.txt](../ChatHistoryAnalyst/data/relationship.txt) | 停用项目 · 历史源码/依赖/配置 |
| [ChatHistoryAnalyst/docker-compose.yml](../ChatHistoryAnalyst/docker-compose.yml) | 停用项目 · 历史源码/依赖/配置 |
| [ChatHistoryAnalyst/docs/rag-roadmap.md](../ChatHistoryAnalyst/docs/rag-roadmap.md) | 停用项目 · RAG 后续演进路线 |
| [ChatHistoryAnalyst/docs/如何导入正确格式.md](../ChatHistoryAnalyst/docs/%E5%A6%82%E4%BD%95%E5%AF%BC%E5%85%A5%E6%AD%A3%E7%A1%AE%E6%A0%BC%E5%BC%8F.md) | 停用项目 · 如何导入正确格式？ |
| [ChatHistoryAnalyst/front/frontend.py](../ChatHistoryAnalyst/front/frontend.py) | 停用项目 · _get_chats、_build_payload |
| [ChatHistoryAnalyst/import_knowledge.py](../ChatHistoryAnalyst/import_knowledge.py) | 停用项目 · 历史源码/依赖/配置 |
| [ChatHistoryAnalyst/pyproject.toml](../ChatHistoryAnalyst/pyproject.toml) | 停用项目 · 历史源码/依赖/配置 |
| [ChatHistoryAnalyst/src/__init__.py](../ChatHistoryAnalyst/src/__init__.py) | 停用项目 · 历史源码/依赖/配置 |
| [ChatHistoryAnalyst/src/context_engineer.py](../ChatHistoryAnalyst/src/context_engineer.py) | 停用项目 · _quick_hash、_parse_time |
| [ChatHistoryAnalyst/src/core_llm.py](../ChatHistoryAnalyst/src/core_llm.py) | 停用项目 · 历史源码/依赖/配置 |
| [ChatHistoryAnalyst/src/main.py](../ChatHistoryAnalyst/src/main.py) | 停用项目 · _parse_text_lines、import_chat_data |
| [ChatHistoryAnalyst/src/rag_function.py](../ChatHistoryAnalyst/src/rag_function.py) | 停用项目 · _get_embedding_dim、_get_stored_vector_dim |
| [ChatHistoryAnalyst/src/schemas.py](../ChatHistoryAnalyst/src/schemas.py) | 停用项目 · ChatMessage、AnalysisRequest |
| [ChatHistoryAnalyst/src/skills/__init__.py](../ChatHistoryAnalyst/src/skills/__init__.py) | 停用项目 · 历史源码/依赖/配置 |
| [ChatHistoryAnalyst/src/skills/skill01_imitate.py](../ChatHistoryAnalyst/src/skills/skill01_imitate.py) | 停用项目 · execute_imitate_skill、_build_chat_summary |
| [ChatHistoryAnalyst/src/skills/skill02_emotion.py](../ChatHistoryAnalyst/src/skills/skill02_emotion.py) | 停用项目 · execute_emotion_skill、_build_chat_summary |
| [ChatHistoryAnalyst/src/skills/skill03_atmosphere.py](../ChatHistoryAnalyst/src/skills/skill03_atmosphere.py) | 停用项目 · execute_atmosphere_skill、_build_chat_summary |
| [ChatHistoryAnalyst/src/tools.py](../ChatHistoryAnalyst/src/tools.py) | 停用项目 · search_psychology_knowledge、search_chat_context |
| [ChatHistoryAnalyst/uv.lock](../ChatHistoryAnalyst/uv.lock) | 停用项目 · 历史源码/依赖/配置 |

## Journal

| 文件 | 定位 |
| --- | --- |
| [Journal/.gitignore](../Journal/.gitignore) | 版本/构建上下文排除规则 |
| [Journal/Dockerfile](../Journal/Dockerfile) | 所属服务镜像构建 |
| [Journal/alembic.ini](../Journal/alembic.ini) | 数据库迁移/版本管理；执行前核对目标库 |
| [Journal/app.py](../Journal/app.py) | Journal 全部 ORM/会话/CRUD/图片/页面路由 |
| [Journal/create_user.py](../Journal/create_user.py) | 交互/环境创建用户；同名用户会重设密码 |
| [Journal/docker-compose.yml](../Journal/docker-compose.yml) | 子服务配置；由 Portal 根 include，不自包含基础设施 |
| [Journal/migrations/env.py](../Journal/migrations/env.py) | 数据库迁移/版本管理；执行前核对目标库 |
| [Journal/migrations/script.py.mako](../Journal/migrations/script.py.mako) | 数据库迁移/版本管理；执行前核对目标库 |
| [Journal/migrations/versions/0001_initial.py](../Journal/migrations/versions/0001_initial.py) | 数据库迁移/版本管理；执行前核对目标库 |
| [Journal/migrations/versions/0002_entry_images.py](../Journal/migrations/versions/0002_entry_images.py) | 数据库迁移/版本管理；执行前核对目标库 |
| [Journal/pyproject.toml](../Journal/pyproject.toml) | Python 项目与依赖声明 |
| [Journal/requirements.txt](../Journal/requirements.txt) | 兼容依赖列表；安装以 pyproject/uv.lock 为准 |
| [Journal/static/avatar.jpg](../Journal/static/avatar.jpg) | 二进制静态媒体；仅核对路径/类型 |
| [Journal/static/journal.css](../Journal/static/journal.css) | 页面视觉样式 |
| [Journal/static/journal.html](../Journal/static/journal.html) | 页面结构/显示入口 |
| [Journal/static/journal.js](../Journal/static/journal.js) | 浏览器交互/接口调用 |
| [Journal/static/login.html](../Journal/static/login.html) | 页面结构/显示入口 |
| [Journal/static/login.js](../Journal/static/login.js) | 浏览器交互/接口调用 |
| [Journal/tests/test_images.py](../Journal/tests/test_images.py) | journal_test 专用图片集成测试；会删建表 |
| [Journal/uv.lock](../Journal/uv.lock) | Python 精确依赖锁；以所属子项目为边界 |

## dude Python、前端与测试

| 文件 | 定位 |
| --- | --- |
| [dude/.env.example](../dude/.env.example) | 环境模板（不是实际凭证） |
| [dude/.gitignore](../dude/.gitignore) | 版本/构建上下文排除规则 |
| [dude/CLAUDE.md](../dude/CLAUDE.md) | dude 模型地图、真实节点与 00–08 定位 |
| [dude/Dockerfile](../dude/Dockerfile) | 所属服务镜像构建 |
| [dude/PRODUCT.md](../dude/PRODUCT.md) | 确认的产品范围、只交付方案与默认原则 |
| [dude/README.md](../dude/README.md) | dude — 面向新手的 Vibe Coding 方案助手 |
| [dude/app.py](../dude/app.py) | FastAPI 初始化、路由注入、静态挂载、就绪检查 |
| [dude/config.py](../dude/config.py) | DB_* 优先、PG_* 回退；向量记忆停用、Wiki 发布路径与种子开关 |
| [dude/core/__init__.py](../dude/core/__init__.py) | Python 包入口 |
| [dude/core/agent.py](../dude/core/agent.py) | 会话/上下文装配、图执行、SSE、保存与终态 |
| [dude/core/context_engine.py](../dude/core/context_engine.py) | 实现入口：`ConversationContext`、`ContextEngine`、`_count_turns`、`_extract_last_turn` |
| [dude/core/graph.py](../dude/core/graph.py) | 当前公开规划图、并行缺口、文案审核、用量采集 |
| [dude/core/llm_client.py](../dude/core/llm_client.py) | 环境驱动模型工厂；未接 admin_model_configs |
| [dude/core/planning.py](../dude/core/planning.py) | 核心信息、默认来源、问题批量、输出结构校验 |
| [dude/core/router.py](../dude/core/router.py) | 旧意图分类器；当前 router_node 不调用 |
| [dude/data/.gitignore](../dude/data/.gitignore) | 版本/构建上下文排除规则 |
| [dude/data/exports/.gitkeep](../dude/data/exports/.gitkeep) | 空目录版本占位 |
| [dude/docker-compose.yml](../dude/docker-compose.yml) | 子服务配置；由 Portal 根 include，不自包含基础设施 |
| [dude/memory/__init__.py](../dude/memory/__init__.py) | 历史记忆机制，当前 Agent 不初始化 |
| [dude/memory/session_memory.py](../dude/memory/session_memory.py) | 历史向量记忆，主链路停用，数据不删除 |
| [dude/memory/user_profile.py](../dude/memory/user_profile.py) | 历史跨会话画像，主链路停用，产品设计未定 |
| [dude/models/__init__.py](../dude/models/__init__.py) | Python 包入口 |
| [dude/models/schemas.py](../dude/models/schemas.py) | 实现入口：`ChatRequest`、`ChatMessage`、`SSEEventType`、`SessionEvent` |
| [dude/models/task_contract.py](../dude/models/task_contract.py) | 实现入口：`Scope`、`Permissions`、`TaskContract`、`_migrate_legacy_plan` |
| [dude/prompts/__init__.py](../dude/prompts/__init__.py) | Python 包入口 |
| [dude/prompts/system_prompts.py](../dude/prompts/system_prompts.py) | 辅助配置/资料；按路径所属模块阅读 |
| [dude/prompts/templates.py](../dude/prompts/templates.py) | 实现入口：`build_dimensions_desc`、`format_expressed_dimensions`、`get_dimension_hint`、`get_clarification_templates` |
| [dude/pyproject.toml](../dude/pyproject.toml) | Python 项目与依赖声明 |
| [dude/requirements.txt](../dude/requirements.txt) | 兼容依赖列表；安装以 pyproject/uv.lock 为准 |
| [dude/routers/__init__.py](../dude/routers/__init__.py) | Python 包入口 |
| [dude/routers/chat.py](../dude/routers/chat.py) | POST message SSE 与契约 GET/confirm/update |
| [dude/routers/deps.py](../dude/routers/deps.py) | Python JWT 解析及 require_user |
| [dude/routers/feedback.py](../dude/routers/feedback.py) | 实现入口：`set_agent`、`submit_feedback`、`get_feedback_stats` |
| [dude/routers/files.py](../dude/routers/files.py) | save/download 导出文件；无 upload |
| [dude/routers/handover.py](../dude/routers/handover.py) | POST sessions/import 旧交接资料解析 |
| [dude/routers/knowledge.py](../dude/routers/knowledge.py) | search/stats/reindex；无 upload |
| [dude/routers/sessions.py](../dude/routers/sessions.py) | 会话列表/详情/删除/完整聊天导出 |
| [dude/services/__init__.py](../dude/services/__init__.py) | Python 包入口 |
| [dude/services/contract_store.py](../dude/services/contract_store.py) | 契约版本/确认持久化，启动建表 |
| [dude/services/document_processor.py](../dude/services/document_processor.py) | 实现入口：`SourceMetadata`、`ChunkIdentity`、`SourceParser`、`SourceSplitter` |
| [dude/services/engineering_advisor.py](../dude/services/engineering_advisor.py) | 旧工程建议服务；不是当前图节点 |
| [dude/services/handover_service.py](../dude/services/handover_service.py) | 实现入口：`HandoverService` |
| [dude/services/md_export.py](../dude/services/md_export.py) | 实现入口：`export_session_to_md`、`load_md_file`、`load_multiple_md_files` |
| [dude/services/multi_agent.py](../dude/services/multi_agent.py) | 旧三立场 Panel；不是当前 gap_analysis 实现 |
| [dude/services/rag_service.py](../dude/services/rag_service.py) | 历史 RAGService；主链路不初始化或调用 |
| [dude/services/session_store.py](../dude/services/session_store.py) | 会话/消息/反馈，同步 PostgreSQL 与启动建表 |
| [dude/services/usage_service.py](../dude/services/usage_service.py) | 异步写 admin_token_usage，DB_* 优先于 PG_* |
| [dude/services/vector_store.py](../dude/services/vector_store.py) | 历史向量/知识/记忆存储，主链路不初始化 |
| [dude/skills/__init__.py](../dude/skills/__init__.py) | 旧技能/工具兼容实现；当前生成节点不绑定执行工具 |
| [dude/skills/base.py](../dude/skills/base.py) | 旧技能/工具兼容实现；当前生成节点不绑定执行工具 |
| [dude/skills/code_review.py](../dude/skills/code_review.py) | 旧技能/工具兼容实现；当前生成节点不绑定执行工具 |
| [dude/skills/info_retention.py](../dude/skills/info_retention.py) | 旧技能/工具兼容实现；当前生成节点不绑定执行工具 |
| [dude/skills/prompt_refiner.py](../dude/skills/prompt_refiner.py) | 旧技能/工具兼容实现；当前生成节点不绑定执行工具 |
| [dude/skills/work_arranger.py](../dude/skills/work_arranger.py) | 旧技能/工具兼容实现；当前生成节点不绑定执行工具 |
| [dude/static/css/style.css](../dude/static/css/style.css) | 页面视觉样式 |
| [dude/static/index.html](../dude/static/index.html) | 页面结构/显示入口 |
| [dude/static/js/chat.js](../dude/static/js/chat.js) | 浏览器交互/接口调用 |
| [dude/static/source/dude.jpg](../dude/static/source/dude.jpg) | 二进制静态媒体；仅核对路径/类型 |
| [dude/tests/__init__.py](../dude/tests/__init__.py) | 回归测试；运行条件见架构验证表 |
| [dude/tests/test_auth_routing.py](../dude/tests/test_auth_routing.py) | nginx 真实隔离代理测试；缺 nginx/openssl 跳过 |
| [dude/tests/test_graph.py](../dude/tests/test_graph.py) | 回归测试；运行条件见架构验证表 |
| [dude/tests/test_planning.py](../dude/tests/test_planning.py) | 回归测试；运行条件见架构验证表 |
| [dude/tests/test_planning_flow.py](../dude/tests/test_planning_flow.py) | 回归测试；运行条件见架构验证表 |
| [dude/tests/test_session_store.py](../dude/tests/test_session_store.py) | 真实 PostgreSQL 存储测试；会按配置写库 |
| [dude/tests/test_usage_identity.py](../dude/tests/test_usage_identity.py) | 回归测试；运行条件见架构验证表 |
| [dude/tools/__init__.py](../dude/tools/__init__.py) | 旧技能/工具兼容实现；当前生成节点不绑定执行工具 |
| [dude/tools/code.py](../dude/tools/code.py) | 旧技能/工具兼容实现；当前生成节点不绑定执行工具 |
| [dude/tools/fs.py](../dude/tools/fs.py) | 旧技能/工具兼容实现；当前生成节点不绑定执行工具 |
| [dude/tools/knowledge.py](../dude/tools/knowledge.py) | 旧技能/工具兼容实现；当前生成节点不绑定执行工具 |
| [dude/tools/memory.py](../dude/tools/memory.py) | 旧技能/工具兼容实现；当前生成节点不绑定执行工具 |
| [dude/tools/search.py](../dude/tools/search.py) | 旧技能/工具兼容实现；当前生成节点不绑定执行工具 |
| [dude/tools/shell.py](../dude/tools/shell.py) | 旧技能/工具兼容实现；当前生成节点不绑定执行工具 |
| [dude/uv.lock](../dude/uv.lock) | Python 精确依赖锁；以所属子项目为边界 |

## dude-admin

| 文件 | 定位 |
| --- | --- |
| [dude/dude-admin/Dockerfile](../dude/dude-admin/Dockerfile) | 所属服务镜像构建 |
| [dude/dude-admin/README.md](../dude/dude-admin/README.md) | dude-admin — dude 管理后台 |
| [dude/dude-admin/cmd/gateway/main.go](../dude/dude-admin/cmd/gateway/main.go) | Go 启动、SQL 迁移、seed、所有 Go 路由 |
| [dude/dude-admin/cmd/healthcheck/main.go](../dude/dude-admin/cmd/healthcheck/main.go) | 辅助配置/资料；按路径所属模块阅读 |
| [dude/dude-admin/config/config.go](../dude/dude-admin/config/config.go) | 辅助配置/资料；按路径所属模块阅读 |
| [dude/dude-admin/docker-compose.yml](../dude/dude-admin/docker-compose.yml) | 子服务配置；由 Portal 根 include，不自包含基础设施 |
| [dude/dude-admin/go.mod](../dude/dude-admin/go.mod) | Go 模块声明/校验锁 |
| [dude/dude-admin/go.sum](../dude/dude-admin/go.sum) | Go 模块声明/校验锁 |
| [dude/dude-admin/internal/handler/auth.go](../dude/dude-admin/internal/handler/auth.go) | 辅助配置/资料；按路径所属模块阅读 |
| [dude/dude-admin/internal/handler/context.go](../dude/dude-admin/internal/handler/context.go) | 辅助配置/资料；按路径所属模块阅读 |
| [dude/dude-admin/internal/handler/middleware.go](../dude/dude-admin/internal/handler/middleware.go) | JWT、admin 角色、请求日志中间件 |
| [dude/dude-admin/internal/handler/model.go](../dude/dude-admin/internal/handler/model.go) | 辅助配置/资料；按路径所属模块阅读 |
| [dude/dude-admin/internal/handler/stats.go](../dude/dude-admin/internal/handler/stats.go) | 辅助配置/资料；按路径所属模块阅读 |
| [dude/dude-admin/internal/handler/users.go](../dude/dude-admin/internal/handler/users.go) | 管理员用户目录和概览路由/参数校验 |
| [dude/dude-admin/internal/handler/users_test.go](../dude/dude-admin/internal/handler/users_test.go) | 辅助配置/资料；按路径所属模块阅读 |
| [dude/dude-admin/internal/model/models.go](../dude/dude-admin/internal/model/models.go) | 辅助配置/资料；按路径所属模块阅读 |
| [dude/dude-admin/internal/service/auth.go](../dude/dude-admin/internal/service/auth.go) | 辅助配置/资料；按路径所属模块阅读 |
| [dude/dude-admin/internal/service/model.go](../dude/dude-admin/internal/service/model.go) | 辅助配置/资料；按路径所属模块阅读 |
| [dude/dude-admin/internal/service/stats.go](../dude/dude-admin/internal/service/stats.go) | 辅助配置/资料；按路径所属模块阅读 |
| [dude/dude-admin/internal/service/users.go](../dude/dude-admin/internal/service/users.go) | 用户筛选分页、近 30 天用量 SQL |
| [dude/dude-admin/internal/store/postgres.go](../dude/dude-admin/internal/store/postgres.go) | 辅助配置/资料；按路径所属模块阅读 |
| [dude/dude-admin/migrations/001_init.down.sql](../dude/dude-admin/migrations/001_init.down.sql) | 数据库迁移/版本管理；执行前核对目标库 |
| [dude/dude-admin/migrations/001_init.up.sql](../dude/dude-admin/migrations/001_init.up.sql) | 数据库迁移/版本管理；执行前核对目标库 |
| [dude/dude-admin/pkg/response/response.go](../dude/dude-admin/pkg/response/response.go) | 辅助配置/资料；按路径所属模块阅读 |
| [dude/dude-admin/static/admin.html](../dude/dude-admin/static/admin.html) | 页面结构/显示入口 |
| [dude/dude-admin/static/css/admin.css](../dude/dude-admin/static/css/admin.css) | 页面视觉样式 |
| [dude/dude-admin/static/css/login.css](../dude/dude-admin/static/css/login.css) | 页面视觉样式 |
| [dude/dude-admin/static/js/admin.js](../dude/dude-admin/static/js/admin.js) | 浏览器交互/接口调用 |
| [dude/dude-admin/static/js/auth.js](../dude/dude-admin/static/js/auth.js) | 浏览器交互/接口调用 |
| [dude/dude-admin/static/login.html](../dude/dude-admin/static/login.html) | 页面结构/显示入口 |
| [dude/dude-admin/tests/auth.test.cjs](../dude/dude-admin/tests/auth.test.cjs) | Node 认证、前端 DOM/SSE、目录与用量模拟测试 |

## dude 文档与学习资料

| 文件 | 定位 |
| --- | --- |
| [dude/docs/agent-course/00-概述-架构全景图.md](../dude/docs/agent-course/00-%E6%A6%82%E8%BF%B0-%E6%9E%B6%E6%9E%84%E5%85%A8%E6%99%AF%E5%9B%BE.md) | 旧架构教学资料（非当前节点依据） |
| [dude/docs/agent-course/01-Agent入口与生命周期.md](../dude/docs/agent-course/01-Agent%E5%85%A5%E5%8F%A3%E4%B8%8E%E7%94%9F%E5%91%BD%E5%91%A8%E6%9C%9F.md) | 旧架构教学资料（非当前节点依据） |
| [dude/docs/agent-course/02-图与状态机.md](../dude/docs/agent-course/02-%E5%9B%BE%E4%B8%8E%E7%8A%B6%E6%80%81%E6%9C%BA.md) | 旧架构教学资料（非当前节点依据） |
| [dude/docs/agent-course/03-意图路由.md](../dude/docs/agent-course/03-%E6%84%8F%E5%9B%BE%E8%B7%AF%E7%94%B1.md) | 旧架构教学资料（非当前节点依据） |
| [dude/docs/agent-course/04-上下文引擎.md](../dude/docs/agent-course/04-%E4%B8%8A%E4%B8%8B%E6%96%87%E5%BC%95%E6%93%8E.md) | 旧架构教学资料（非当前节点依据） |
| [dude/docs/agent-course/05-Planner节点.md](../dude/docs/agent-course/05-Planner%E8%8A%82%E7%82%B9.md) | 旧架构教学资料（非当前节点依据） |
| [dude/docs/agent-course/06-追问系统.md](../dude/docs/agent-course/06-%E8%BF%BD%E9%97%AE%E7%B3%BB%E7%BB%9F.md) | 旧架构教学资料（非当前节点依据） |
| [dude/docs/agent-course/07-工程规范检查.md](../dude/docs/agent-course/07-%E5%B7%A5%E7%A8%8B%E8%A7%84%E8%8C%83%E6%A3%80%E6%9F%A5.md) | 旧架构教学资料（非当前节点依据） |
| [dude/docs/agent-course/08-多Agent-Panel.md](../dude/docs/agent-course/08-%E5%A4%9AAgent-Panel.md) | 旧架构教学资料（非当前节点依据） |
| [dude/docs/agent-course/09-执行节点.md](../dude/docs/agent-course/09-%E6%89%A7%E8%A1%8C%E8%8A%82%E7%82%B9.md) | 旧架构教学资料（非当前节点依据） |
| [dude/docs/agent-course/10-Checkpoint与Reflect.md](../dude/docs/agent-course/10-Checkpoint%E4%B8%8EReflect.md) | 旧架构教学资料（非当前节点依据） |
| [dude/docs/agent-course/11-RAG系统.md](../dude/docs/agent-course/11-RAG%E7%B3%BB%E7%BB%9F.md) | 旧架构教学资料（非当前节点依据） |
| [dude/docs/agent-course/12-记忆系统.md](../dude/docs/agent-course/12-%E8%AE%B0%E5%BF%86%E7%B3%BB%E7%BB%9F.md) | 旧架构教学资料（非当前节点依据） |
| [dude/docs/agent-course/13-Skills与工具.md](../dude/docs/agent-course/13-Skills%E4%B8%8E%E5%B7%A5%E5%85%B7.md) | 旧架构教学资料（非当前节点依据） |
| [dude/docs/agent-course/14-任务契约.md](../dude/docs/agent-course/14-%E4%BB%BB%E5%8A%A1%E5%A5%91%E7%BA%A6.md) | 旧架构教学资料（非当前节点依据） |
| [dude/docs/agent-course/15-流式输出.md](../dude/docs/agent-course/15-%E6%B5%81%E5%BC%8F%E8%BE%93%E5%87%BA.md) | 旧架构教学资料（非当前节点依据） |
| [dude/docs/agent-course/16-配置与LLM工厂.md](../dude/docs/agent-course/16-%E9%85%8D%E7%BD%AE%E4%B8%8ELLM%E5%B7%A5%E5%8E%82.md) | 旧架构教学资料（非当前节点依据） |
| [dude/docs/capability-and-tools.md](../dude/docs/capability-and-tools.md) | dude能力边界与工具使用规范 |
| [dude/docs/detection-strategy.md](../dude/docs/detection-strategy.md) | 检测体系设计 |
| [dude/docs/done/agent-audit-2026-07-20.md](../dude/docs/done/agent-audit-2026-07-20.md) | 历史设计/问题记录 · dude Agent 审计报告 |
| [dude/docs/done/context-engineering-guide.md](../dude/docs/done/context-engineering-guide.md) | 历史设计/问题记录 · Context Engineering 实战指南 |
| [dude/docs/done/hallucination-prevention.md](../dude/docs/done/hallucination-prevention.md) | 历史设计/问题记录 · Hallucination Prevention Guide -- 幻觉从哪来、怎么层层拦截 |
| [dude/docs/done/harness-engineering-guide.md](../dude/docs/done/harness-engineering-guide.md) | 历史设计/问题记录 · Harness Engineering 学习指南 — 从 Prompt 到全链路驾驭 |
| [dude/docs/done/three-layer-rag.md](../dude/docs/done/three-layer-rag.md) | 历史设计/问题记录 · Three-Layer RAG -- 稠密+稀疏+知识图谱混合检索 |
| [dude/docs/frontend-refresh.md](../dude/docs/frontend-refresh.md) | dude 浅色对话界面 |
| [dude/docs/interview-answer-key.md](../dude/docs/interview-answer-key.md) | 学习/面试材料 · 面试对照答案 — dude 项目拷打 |
| [dude/docs/interview-explanations.md](../dude/docs/interview-explanations.md) | 学习/面试材料 · 面试题讲解 — 你标了"？？？"的两道 |
| [dude/docs/interview-prep-testing.md](../dude/docs/interview-prep-testing.md) | 学习/面试材料 · 测试面试试训文档 — 基于 dude (Portal) 项目实战 |
| [dude/docs/interview-project-grilling.md](../dude/docs/interview-project-grilling.md) | 学习/面试材料 · 项目拷打面试流程 — dude (AI Agent) |
| [dude/docs/ops-guide.md](../dude/docs/ops-guide.md) | 运维实操手册 — 日志、Badcase、监控 |
| [dude/docs/product-modules.md](../dude/docs/product-modules.md) | dude 板块划分与逐块修改约定 |
| [dude/docs/product-roadmap.md](../dude/docs/product-roadmap.md) | dude 逐步优化路线 |
| [dude/docs/rag-pipeline-principles.md](../dude/docs/rag-pipeline-principles.md) | RAG 检索·编排·过滤原理详解 |
| [dude/docs/semantic-drift.md](../dude/docs/semantic-drift.md) | 语义偏移：多节点 Agent 冲突与重试机制 |
| [dude/docs/task-contract-guide.md](../dude/docs/task-contract-guide.md) | 任务契约 (TaskContract) — 设计教程 |
| [dude/docs/three-layer-memory-design.md](../dude/docs/three-layer-memory-design.md) | 三层 Memory 设计 |
| [dude/docs/to_log/badcase-review-guide.md](../dude/docs/to_log/badcase-review-guide.md) | 历史设计/问题记录 · Badcase 复盘指南 |
| [dude/docs/to_log/debug-report-2026-07-14.md](../dude/docs/to_log/debug-report-2026-07-14.md) | 历史设计/问题记录 · 调试报告 — 2026-07-14 |
| [dude/docs/to_log/log-management-guide.md](../dude/docs/to_log/log-management-guide.md) | 历史设计/问题记录 · 日志管理指南 |
| [dude/docs/token-management-guide.md](../dude/docs/token-management-guide.md) | Token 监管指南 |
| [dude/docs/tool-loop-prevention.md](../dude/docs/tool-loop-prevention.md) | 工具防循环指南 — Agent 为什么打转、怎么拦住它 |
| [dude/docs/错题集/Q2.2.md](../dude/docs/%E9%94%99%E9%A2%98%E9%9B%86/Q2.2.md) | 学习/面试材料 · Q2.2 AgentState 挂了哪些字段 |
| [dude/docs/错题集/Q3.1.2.md](../dude/docs/%E9%94%99%E9%A2%98%E9%9B%86/Q3.1.2.md) | 学习/面试材料 · Q3.1.2 L3 事实在 PGVector 里以什么粒度存储 |
| [dude/docs/错题集/Q3.1.4.md](../dude/docs/%E9%94%99%E9%A2%98%E9%9B%86/Q3.1.4.md) | 学习/面试材料 · Q3.1.4 话题切换中间地带真的调了 LLM 精检吗 |
| [dude/docs/错题集/Q3.1.6.md](../dude/docs/%E9%94%99%E9%A2%98%E9%9B%86/Q3.1.6.md) | 学习/面试材料 · Q3.1.6 "跨会话可用"和按 session_id 过滤矛盾吗 |
| [dude/docs/错题集/Q3.2.4.md](../dude/docs/%E9%94%99%E9%A2%98%E9%9B%86/Q3.2.4.md) | 学习/面试材料 · Q3.2.4 score 是什么尺度，sparse-only 文档能过 0.6 吗 |
| [dude/docs/错题集/Q3.2.5.md](../dude/docs/%E9%94%99%E9%A2%98%E9%9B%86/Q3.2.5.md) | 学习/面试材料 · Q3.2.5 "BM25" 实际是什么，GIN 索引生效吗 |
| [dude/docs/错题集/Q3.2.7.md](../dude/docs/%E9%94%99%E9%A2%98%E9%9B%86/Q3.2.7.md) | 学习/面试材料 · Q3.2.7 关键词加权对中文查询生效吗 |
| [dude/docs/错题集/Q3.3.1.md](../dude/docs/%E9%94%99%E9%A2%98%E9%9B%86/Q3.3.1.md) | 学习/面试材料 · Q3.3.1 真是"规则 + LLM 两阶段"吗，confidence 谁给的 |
| [dude/docs/错题集/Q3.3.3.md](../dude/docs/%E9%94%99%E9%A2%98%E9%9B%86/Q3.3.3.md) | 学习/面试材料 · Q3.3.3 6 场景互斥硬判的局限 |
| [dude/docs/错题集/Q3.4.1.md](../dude/docs/%E9%94%99%E9%A2%98%E9%9B%86/Q3.4.1.md) | 学习/面试材料 · Q3.4.1 completeness 是代码算的还是 LLM 估的 |
| [dude/docs/错题集/Q3.4.3.md](../dude/docs/%E9%94%99%E9%A2%98%E9%9B%86/Q3.4.3.md) | 学习/面试材料 · Q3.4.3 scope.out 为什么比 in 更重要 |
| [dude/docs/错题集/Q3.4.4.md](../dude/docs/%E9%94%99%E9%A2%98%E9%9B%86/Q3.4.4.md) | 学习/面试材料 · Q3.4.4 JSON 三层降级分别是什么 |
| [dude/docs/错题集/Q3.4.5.md](../dude/docs/%E9%94%99%E9%A2%98%E9%9B%86/Q3.4.5.md) | 学习/面试材料 · Q3.4.5 _fallback_plan 什么时候触发，用什么判断完整度 |
| [dude/docs/错题集/Q3.5.2.md](../dude/docs/%E9%94%99%E9%A2%98%E9%9B%86/Q3.5.2.md) | 学习/面试材料 · Q3.5.2 execute 里 ReAct 建了几次，skill.execute 什么时候被调 |
| [dude/docs/错题集/Q3.5.3.md](../dude/docs/%E9%94%99%E9%A2%98%E9%9B%86/Q3.5.3.md) | 学习/面试材料 · Q3.5.3 bind_tools 和 create_react_agent 各自干什么 |
| [dude/docs/错题集/Q3.5.4.md](../dude/docs/%E9%94%99%E9%A2%98%E9%9B%86/Q3.5.4.md) | 学习/面试材料 · Q3.5.4 3 个工具为什么不分配给任何 skill |
| [dude/docs/错题集/Q3.5.5.md](../dude/docs/%E9%94%99%E9%A2%98%E9%9B%86/Q3.5.5.md) | 学习/面试材料 · Q3.5.5 ReAct 循环有轮数上限吗 |
| [dude/docs/错题集/Q3.5.6.md](../dude/docs/%E9%94%99%E9%A2%98%E9%9B%86/Q3.5.6.md) | 学习/面试材料 · Q3.5.6 子图 token 能冒泡到外层 astream_events 吗 |
| [dude/docs/错题集/Q3.6.1.md](../dude/docs/%E9%94%99%E9%A2%98%E9%9B%86/Q3.6.1.md) | 学习/面试材料 · Q3.6.1 三级输出模式，分级依据 |
| [dude/docs/错题集/Q3.6.2.md](../dude/docs/%E9%94%99%E9%A2%98%E9%9B%86/Q3.6.2.md) | 学习/面试材料 · Q3.6.2 "降级匹配"为什么叫降级，现在是唯一路径吗 |
| [dude/docs/错题集/Q3.6.3.md](../dude/docs/%E9%94%99%E9%A2%98%E9%9B%86/Q3.6.3.md) | 学习/面试材料 · Q3.6.3 命中多场景时 mode 怎么定 |
| [dude/docs/错题集/Q3.8.2.md](../dude/docs/%E9%94%99%E9%A2%98%E9%9B%86/Q3.8.2.md) | 学习/面试材料 · Q3.8.2 25 个测试覆盖了什么 |
| [dude/docs/错题集/Q3.9.2.md](../dude/docs/%E9%94%99%E9%A2%98%E9%9B%86/Q3.9.2.md) | 学习/面试材料 · Q3.9.2 embedding 整体挂了，完整降级链怎么串 |
| [dude/docs/错题集/Q4.1.md](../dude/docs/%E9%94%99%E9%A2%98%E9%9B%86/Q4.1.md) | 学习/面试材料 · Q4.1 100 用户并发，哪里先出问题 |
| [dude/docs/错题集/Q4.2.md](../dude/docs/%E9%94%99%E9%A2%98%E9%9B%86/Q4.2.md) | 学习/面试材料 · Q4.2 知识库涨到 20 万 md，哪里先瓶颈 |
| [dude/docs/错题集/Q4.4.md](../dude/docs/%E9%94%99%E9%A2%98%E9%9B%86/Q4.4.md) | 学习/面试材料 · Q4.4 1M 窗口下，三层上下文 + RAG 会不会浪费 |
| [dude/docs/错题集/Q4.5.md](../dude/docs/%E9%94%99%E9%A2%98%E9%9B%86/Q4.5.md) | 学习/面试材料 · Q4.5 加定时任务/主动推送，冲突在哪 |
| [dude/docs/错题集/README.md](../dude/docs/%E9%94%99%E9%A2%98%E9%9B%86/README.md) | 学习/面试材料 · 错题集 — dude 项目拷打 |
| [dude/docs/dude](../dude/docs/%E9%98%BF%E7%A6%8F) | 辅助配置/资料；按路径所属模块阅读 |
| [dude/docs/dude能力边界与工具使用规范-v1.0.txt](../dude/docs/%E9%98%BF%E7%A6%8F%E8%83%BD%E5%8A%9B%E8%BE%B9%E7%95%8C%E4%B8%8E%E5%B7%A5%E5%85%B7%E4%BD%BF%E7%94%A8%E8%A7%84%E8%8C%83-v1.0.txt) | 辅助配置/资料；按路径所属模块阅读 |

## dude 知识参考

| 文件 | 定位 |
| --- | --- |
| [dude/knowledge_base/coding_skills/skills_20.md](../dude/knowledge_base/coding_skills/skills_20.md) | RAG 参考数据 · dude Skill 知识卡片集（20张） |
| [dude/knowledge_base/engineering/api_credentials.md](../dude/knowledge_base/engineering/api_credentials.md) | RAG 参考数据 · API 密钥与凭证管理 |
| [dude/knowledge_base/engineering/data_safety.md](../dude/knowledge_base/engineering/data_safety.md) | RAG 参考数据 · 数据库操作 — 安全红线 |
| [dude/knowledge_base/engineering/git_security.md](../dude/knowledge_base/engineering/git_security.md) | RAG 参考数据 · 公开提交 Git 仓库 — 安全检查清单 |
| [dude/knowledge_base/engineering/python_deps.md](../dude/knowledge_base/engineering/python_deps.md) | RAG 参考数据 · Python 项目依赖管理 |
| [dude/knowledge_base/prompt_engineering.md](../dude/knowledge_base/prompt_engineering.md) | RAG 参考数据 · 提示词工程最佳实践 |
| [dude/knowledge_base/suggested_tools/tools.md](../dude/knowledge_base/suggested_tools/tools.md) | RAG 参考数据 · dude工具知识卡片集（20张） |
| [dude/knowledge_base/tech_news.md](../dude/knowledge_base/tech_news.md) | RAG 参考数据 · 最新技术和软件工程动态 |
| [dude/knowledge_base/tool_recommendations.md](../dude/knowledge_base/tool_recommendations.md) | RAG 参考数据 · 工具推荐库 |
| [dude/knowledge_base/workflow_best_practices.md](../dude/knowledge_base/workflow_best_practices.md) | RAG 参考数据 · 工作流最佳实践 |

## Portal 文档

| 文件 | 定位 |
| --- | --- |
| [docs/dude-admin-architecture.md](../docs/dude-admin-architecture.md) | dude 架构设计 v3 |
| [docs/chatlab-retirement.md](../docs/chatlab-retirement.md) | ChatLab 独立归档与网站下线 |
| [docs/docker-deploy-guide.md](../docs/docker-deploy-guide.md) | Docker 部署学习笔记 |
| [docs/history/model-context-history.md](../docs/history/model-context-history.md) | 旧 Portal/dude Session 记录；按需读，不是当前架构 |
| [docs/interview-prep/01-测试基础与流程.md](../docs/interview-prep/01-%E6%B5%8B%E8%AF%95%E5%9F%BA%E7%A1%80%E4%B8%8E%E6%B5%81%E7%A8%8B.md) | 学习/面试材料 · 01 · 测试基础与流程 |
| [docs/interview-prep/02-用例设计与缺陷管理.md](../docs/interview-prep/02-%E7%94%A8%E4%BE%8B%E8%AE%BE%E8%AE%A1%E4%B8%8E%E7%BC%BA%E9%99%B7%E7%AE%A1%E7%90%86.md) | 学习/面试材料 · 02 · 用例设计与缺陷管理 |
| [docs/interview-prep/03-测试类型与工具.md](../docs/interview-prep/03-%E6%B5%8B%E8%AF%95%E7%B1%BB%E5%9E%8B%E4%B8%8E%E5%B7%A5%E5%85%B7.md) | 学习/面试材料 · 03 · 测试类型与工具 |
| [docs/interview-prep/04-AI辅助与测试报告.md](../docs/interview-prep/04-AI%E8%BE%85%E5%8A%A9%E4%B8%8E%E6%B5%8B%E8%AF%95%E6%8A%A5%E5%91%8A.md) | 学习/面试材料 · 04 · AI 辅助测试 & 测试报告 |
| [docs/interview-prep/05-面试高频20问.md](../docs/interview-prep/05-%E9%9D%A2%E8%AF%95%E9%AB%98%E9%A2%9120%E9%97%AE.md) | 学习/面试材料 · 05 · 面试高频 20 问 |
| [docs/interview-prep/06-测试分类与核心概念.md](../docs/interview-prep/06-%E6%B5%8B%E8%AF%95%E5%88%86%E7%B1%BB%E4%B8%8E%E6%A0%B8%E5%BF%83%E6%A6%82%E5%BF%B5.md) | 学习/面试材料 · 06 · 测试分类与核心概念 |
| [docs/interview-prep/07-协议安全与工具进阶.md](../docs/interview-prep/07-%E5%8D%8F%E8%AE%AE%E5%AE%89%E5%85%A8%E4%B8%8E%E5%B7%A5%E5%85%B7%E8%BF%9B%E9%98%B6.md) | 学习/面试材料 · 07 · 协议安全与工具进阶 |
| [docs/interview-prep/08-敏捷测试与专项测试.md](../docs/interview-prep/08-%E6%95%8F%E6%8D%B7%E6%B5%8B%E8%AF%95%E4%B8%8E%E4%B8%93%E9%A1%B9%E6%B5%8B%E8%AF%95.md) | 学习/面试材料 · 08 · 敏捷测试与专项测试 |
| [docs/interview-prep/09-AI提效测试的方法论.md](../docs/interview-prep/09-AI%E6%8F%90%E6%95%88%E6%B5%8B%E8%AF%95%E7%9A%84%E6%96%B9%E6%B3%95%E8%AE%BA.md) | 学习/面试材料 · 09 · AI 提效测试的方法论 |
| [docs/interview-prep/README.md](../docs/interview-prep/README.md) | 学习/面试材料 · 软件测试面试准备 · 课程文档 |
| [docs/postgresql-backup-and-restore.md](../docs/postgresql-backup-and-restore.md) | PostgreSQL 备份与恢复 |
| [docs/project-context.md](../docs/project-context.md) | 当前架构、API、数据边界、风险与验证索引 |
| [docs/project-file-index.md](../docs/project-file-index.md) | 本清单：版本文件定位 |

## 2026-10-28 部署优化增补

| 文件 | 职责 |
| --- | --- |
| [scripts/build.sh](../scripts/build.sh) | 仅构建指定应用，锁与受限构建器 |
| [scripts/lib/deployment.sh](../scripts/lib/deployment.sh) | 共享部署锁、构建限额、数据库保留、健康检查与代理切换 |
| [ops/buildkit/buildkitd.toml](../ops/buildkit/buildkitd.toml) | BuildKit 内部步骤串行 |
| [dude/dude-admin/.dockerignore](../dude/dude-admin/.dockerignore) | Go 镜像上下文排除密钥与产物 |
| [tests/test_deployment.py](../tests/test_deployment.py) | 假 Docker 故障边界与并发部署测试，不连接数据库 |
| [small-server-deployment.md](small-server-deployment.md) | 日常/首次部署、资源限制、诊断和回退限制 |
