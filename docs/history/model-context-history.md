# 旧模型文档 Session 记录

归档于 2026-10-20，保留此前根级与 dude CLAUDE.md 的历史记录。这些描述对应当时实现，包含已废弃路径、服务、数据库与能力，不能直接作为当前操作步骤。

当前模型入口见 [项目认知](../project-context.md)。本次归档不表示历史事件重新验证。

## 原 Portal Session 记录

### 2026-06-04

1. **清理 ChatHistoryAnalyst/** — 删除冗余文件（nginx/ static/ scripts/ TODO.md course/ portfolio/ proposal.md），已提升至 portal 层
2. **统一 Git 仓库** — 删除嵌套 .git，portal/ 一个 repo 管理所有
3. **首页集成** — FastAPI 挂载首页，打开 :8000 即见首页，/chatlab 重定向到 Streamlit
4. **Makefile** — `make dev` 代替脚本，一个命令起所有服务
5. **文档更新** — 重写 CLAUDE.md / CHANGES.md 对齐真实结构

### 2026-06-09

1. **BGM 修复** — 替换为真实 Frank Ocean 歌单（4首），自动切曲+循环，播放器显示曲目名
2. **删除 tagline** — 移除首页 "AI Infra & Systems Engineer" 标语及相关 CSS/JS
3. **ChatLab 双栏布局** — 左 2/3（导入+三大功能），右 1/3（预览面板），水晶卡片阴影，纯白主题
4. **CORS + API 修复** — chatlab.js 改用相对路径 `/api/v1`，FastAPI 加 CORS 中间件
5. **uv 管理** — portal 层 `pyproject.toml` + `.python-version`，`run_dev.py` 用 `uv run` 启动
6. **CONTROLWEB.md** — 服务器运维手册（部署+域名+HTTPS+Cloudflare+更新流程）
7. **favicon** — 内联 SVG 图标解决标签页转圈
8. **nginx 路由** — 新增 `/bgm/` `/photo/` location 块，BGM 文件去空格

### 2026-07-02

1. **dude 集成** — 将 dude 工作流增强 Agent 作为子项目加入 Portal
2. **架构对齐 ChatLab** — FastAPI + LangChain Agent + @tool，LLM 层从 ~440 行简化为 40 行 ChatOpenAI 工厂
3. **Docker 化** — Dockerfile + docker-compose.yml，dude-api 容器 + volume 持久化
4. **Nginx 路由** — 新增 5 个 location 块：`= /dude`（尾部斜杠重定向），`/dude/css/`、`/dude/js/`（静态资源代理），`/dude/api/`（SSE 流式代理），`/dude/`（首页代理）
5. **首页卡片** — 新增 dude 项目卡片（⚡ New badge）
6. **子路径部署修复** — 前端全部改用相对路径：HTML `href="css/style.css"` + `src="js/..."`, JS `fetch('api/chat/stream')`（去掉前导 `/`），避免与 portal 层的 `/css/` `/js/` `/api/` 冲突
7. **Docker 服务名冲突修复** — dude 服务名 `api` → `dude-api`，解决与 ChatLab 同名 `api` 服务在 docker compose include 时的冲突
8. **模型待配** — SGLang base URL + model 通过 `.env` 注入，明天再配

### 2026-07-03

1. **run_dev.py 三服务** — 新增 dude (:8001) 到本地启动器，与 ChatLab FastAPI (:8000) + Streamlit (:8501) 并列
2. **首页路由补全** — ChatLab FastAPI 新增 `/dude` → 302 重定向到 `localhost:8001`，本地开发点首页卡片即可跳转
3. **端口配置化** — dude `config.py` 新增 `API_HOST` / `API_PORT` 环境变量，app.py `__main__` 块使用配置值
4. **知识库路径修复** — `knowledge_base_dir` 从 `data_dir/knowledge_base` 改为 `project_root/knowledge_base`，修复 Docker 中找不到 KB 文件的问题
5. **文档更新** — CLAUDE.md 架构树 + TODO.md 部署清单对齐三服务架构

## 原 dude Session 记录

以下为历史记录，描述当时的实现，不作为当前部署方式或产品方向的依据。特别是 2026-07-22 的独立仓库、自包含 Compose 和环境读取规则已不适用于当前 Portal checkout。

### 2026-07-27 — Docs 整理

- `docs/` 重组：新增 `done/` 归档目录，迁移已完成的架构设计文档（`agent-audit-2026-07-20.md`、`harness-engineering-guide.md`、`context-engineering-guide.md`、`hallucination-prevention.md`、`three-layer-rag.md`）
- `project-summary.md` 统计更新（文档数 10→18 篇 + 5 篇已归档，commit 数 40+→50+）
- 修复多处交叉引用（`product-vision.md`、`ops-guide.md`、`rag-deep-dive.md` 中指向已移动/不存在文件的链接）
- `dude能力边界与工具使用规范-v1.0.txt` 添加 v2.0 取代声明
- `capability-and-tools.md`、`交互流程图.md` 日期刷新至 2026-07-27

### 2026-07-24 — RAG 来源感知 + 工具卡片

- `rag_service.py`: `ingest_knowledge_base()` glob 修复为 `rglob("*.md")`（子目录原来被忽略）
- `document_processor.py`: 新增 `SourceSplitter._extract_tool_cards()` — `suggested_tools/tools.md` 的 20 张工具卡片自动拆分为独立 Document，卡片级 frontmatter（name/category/source_url/risk_level）提取为独立 metadata
- `ChunkBuilder`: dense/sparse 检索文本加入 `category` 字段，提升分类检索命中率

### 2026-07-24 — 运维性修复

- `.env` 对齐 `.env.example`：补充 15+ 项缺失字段
- `requirements.txt` 同步 `pyproject.toml`：补充 pgvector/aiohttp/numpy/python-multipart
- 多文件修复陈旧引用（SQLite→PostgreSQL、ChromaDB→PGVector、tools 列表更新）

### 2026-07-22 — 独立为 dude 项目

从 Portal/dude 子项目独立为完整项目 dude:
- `config.py`: 移除 `../.env` (Portal 层) 依赖，仅读项目根 `.env`
- `docker-compose.yml`: 新增 `postgres` 服务 (pgvector/pgvector:pg16)，完全自包含
- `.env.example`: 独立环境变量模板
- 服务名: `dude-api` → `dude-api`，DB 名: `chatdemopg` → `alfred`

### 2026-07-11（上午 — 架构升级）

1. **三层上下文架构 (V3)** — `core/context_engine.py` (300+ 行)，L1 滑动窗口 + L2 滚动摘要 + L3 语义事实，替代旧版按轮数阈值切换
2. **Planner 升级为语义中枢** — `core/graph.py` 新增 `checkpoint_node`，Executor 后持续介入检查语义对齐
3. **工具 docstring 三段式** — 12 个工具补齐【用途】【不要用】【优先级】【参数/返回】【限制】标注
4. **约束规范文档** — `boundary.md`，7 个维度的 Harness Engineering 规范 + 附录优先级汇总 + 检查清单

### 2026-07-11（下午 — RAG + 深挖）

5. **Embedding 升级** — `text-embedding-v3` → `text-embedding-v4`
6. **语义分块 (SemanticChunker)** — 相邻句子 embedding 相似度断崖切分
7. **混合检索管道** — Dense + BM25(PG tsvector GIN) → RRF → qwen3-rerank → 相似度过滤 ≥0.6 → 关键词加权
8. **Rerank** — 百炼 qwen3-rerank (120K token/500 docs/100+语言)
9. **上下文驱动 Query 增强** — 去硬编码 scene_keywords，多源信号动态加权 + 话题切换检测
10. **L3 语义事实升级** — regex → LLM 结构化提取，内存字典 → PGVector session_memory
11. **Checkpoint 完成** — 独立 retry 计数器 + L1/L2/RAG 上下文注入 + 幻觉检测维度

### 2026-07-10

1. **V2 架构重写** — 从「正则+模板」升级为「ReAct Agentic Loop」
2. **Prompt 重构** — 删除 200 行正则，维度提取改 LLM structured output
3. **前端升级** — 实时 token 渲染 + 光标动画 + 工具调用指示器 + 👍👎 反馈按钮
4. **反馈系统** — `routers/feedback.py` + PostgreSQL feedback 表 + 统计 API
5. **测试覆盖** — 25 tests
