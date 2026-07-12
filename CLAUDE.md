# Portal — AI 工具集入口

> 多项目统一入口。GitHub: [yoiwerr/portal](https://github.com/yoiwerr/portal)

## 架构

```
~/portal/                          ← Git 仓库根目录
│
├── Makefile                       ← make dev 本地一键启动
├── run_dev.py                     ← 本地三服务启动器
├── docker-compose.yml             ← Docker 编排（include 子项目 + nginx 统一入口）
├── .env.example                   ← 环境变量模板
├── .gitignore
│
├── nginx/default.conf             ← 线上路由: / → 首页, /chatlab → Streamlit, /api → FastAPI, /specific → MakeItSpecific
├── static/                        ← 首页 (纯 HTML/CSS)
│   ├── index.html
│   └── css/style.css
├── scripts/deploy.sh              ← 服务器一键部署
├── TODO.md                        ← 部署清单
│
├── ChatHistoryAnalyst/            ← 子项目: ChatLab
│   ├── pyproject.toml             ← Python 项目标识
│   ├── src/     FastAPI 后端 (8 个 API 端点 + 3 个 Skill Agent)
│   ├── front/   Streamlit 前端
│   ├── data/    心理学参考 .txt
│   ├── docker-compose.yml         ← postgres + api + streamlit
│   └── CLAUDE.md                  ← ChatLab 详细文档
│
└── MakeItSpecific/                  ← 子项目: AI 工作流增强 Agent
    ├── app.py                     ← FastAPI 入口
    ├── config.py                  ← 全局配置 (LLM / RAG / 追问阈值)
    ├── core/     LangGraph 图 + Agent 封装 + LLM 工厂
    ├── routers/  chat(SSE) / sessions / knowledge
    ├── services/ RAG(ChromaDB) / 会话(SQLite) / MD 导出
    ├── skills/   提示词工程 / 工作安排 / 信息留存
    ├── knowledge_base/ 领域知识 .md
    ├── static/   前端 (HTML / CSS / JS)
    ├── docker-compose.yml         ← specific-api
    └── Dockerfile
```

**三层职责:**

| 层 | 职责 | 改什么 |
|----|------|--------|
| portal/ | Docker 编排、nginx 路由、部署脚本 | 上新项目、改路由 |
| ChatHistoryAnalyst/ | ChatLab 业务代码、Python 依赖 | 写功能、修 bug |
| MakeItSpecific/ | 工作流增强 Agent 代码 | 写 Skill、调追问策略 |

## 本地开发

```bash
cd ~/portal
make dev
```

拉起 ChatLab FastAPI (:8000) + ChatLab Streamlit (:8501) + MakeItSpecific (:8001)，`Ctrl+C` 全停。

打开 `http://localhost:8000` → 首页，点项目卡片跳转到对应服务：

| 卡片 | 本地地址 | 说明 |
|------|----------|------|
| ChatLab | `http://localhost:8000/chatlab` | ChatLab HTML 页 |
| MakeItSpecific | `http://localhost:8001` | MakeItSpecific 首页 |
| Streamlit | `http://localhost:8501` | ChatLab 分析界面 |

- FastAPI `/` → `static/index.html`
- FastAPI `/chatlab` → ChatLab 页面
- FastAPI `/specific` → 302 重定向到 `localhost:8001`
- Streamlit 直连 `localhost:8000/api/v1/*`

## 服务器部署

```bash
git clone https://github.com/yoiwerr/portal.git ~/portal
cd ~/portal
cp .env.example .env && vim .env   # 填入密钥，DB_HOST=postgres
chmod +x scripts/deploy.sh && ./scripts/deploy.sh
```

访问 `http://<公网IP>`。nginx 层路由: `/` 首页, `/chatlab` Streamlit, `/api` FastAPI, `/specific` MakeItSpecific。

## 加新子项目范式

```
1. mkdir NewProject && 写 docker-compose.yml
2. docker-compose.yml → include 加一行
3. nginx/default.conf → 加 location 块
4. git add -A && git commit && git push
```

## Session 记录

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

1. **MakeItSpecific 集成** — 将 MakeItSpecific 工作流增强 Agent 作为子项目加入 Portal
2. **架构对齐 ChatLab** — FastAPI + LangChain Agent + @tool，LLM 层从 ~440 行简化为 40 行 ChatOpenAI 工厂
3. **Docker 化** — Dockerfile + docker-compose.yml，specific-api 容器 + volume 持久化
4. **Nginx 路由** — 新增 5 个 location 块：`= /specific`（尾部斜杠重定向），`/specific/css/`、`/specific/js/`（静态资源代理），`/specific/api/`（SSE 流式代理），`/specific/`（首页代理）
5. **首页卡片** — 新增 MakeItSpecific 项目卡片（⚡ New badge）
6. **子路径部署修复** — 前端全部改用相对路径：HTML `href="css/style.css"` + `src="js/..."`, JS `fetch('api/chat/stream')`（去掉前导 `/`），避免与 portal 层的 `/css/` `/js/` `/api/` 冲突
7. **Docker 服务名冲突修复** — MakeItSpecific 服务名 `api` → `specific-api`，解决与 ChatLab 同名 `api` 服务在 docker compose include 时的冲突
8. **模型待配** — SGLang base URL + model 通过 `.env` 注入，明天再配

### 2026-07-03

1. **run_dev.py 三服务** — 新增 MakeItSpecific (:8001) 到本地启动器，与 ChatLab FastAPI (:8000) + Streamlit (:8501) 并列
2. **首页路由补全** — ChatLab FastAPI 新增 `/specific` → 302 重定向到 `localhost:8001`，本地开发点首页卡片即可跳转
3. **端口配置化** — MakeItSpecific `config.py` 新增 `API_HOST` / `API_PORT` 环境变量，app.py `__main__` 块使用配置值
4. **知识库路径修复** — `knowledge_base_dir` 从 `data_dir/knowledge_base` 改为 `project_root/knowledge_base`，修复 Docker 中找不到 KB 文件的问题
5. **文档更新** — CLAUDE.md 架构树 + TODO.md 部署清单对齐三服务架构
