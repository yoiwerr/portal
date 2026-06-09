# Portal

AI 工具集统一入口。GitHub: [yoiwerr/portal](https://github.com/yoiwerr/portal)

## 启动

### 本地开发

```bash
cd ~/portal
make dev
```

拉起 FastAPI (:8000) + Streamlit (:8501)，`Ctrl+C` 全停。打开 `http://localhost:8000`。

### 服务器部署

```bash
git clone https://github.com/yoiwerr/portal.git ~/portal
cd ~/portal
cp .env.example .env && vim .env   # 填入密钥，DB_HOST=postgres
chmod +x scripts/deploy.sh && ./scripts/deploy.sh
```

详细运维见 [CONTROLWEB.md](CONTROLWEB.md)。

## 访问地址

| 内容 | 本地 | 线上 |
|------|------|------|
| 首页 | `http://localhost:8000` | `https://<域名>` |
| ChatLab | `http://localhost:8000/chatlab` | `https://<域名>/chatlab` |
| API 文档 | `http://localhost:8000/api/docs` | `https://<域名>/api/docs` |

---

## 目录总览

```
~/portal/                              ← Git 仓库根目录
│
├── CLAUDE.md                          ← AI 辅助开发指南（本文档的 AI 视角版）
├── README.md                          ← 本文档
├── CHANGES.md                         ← 重构变更记录（2026-06-04）
├── CONTROLWEB.md                      ← 服务器运维手册（部署+域名+HTTPS+更新）
├── TODO.md                            ← 部署清单（step-by-step 勾选列表）
│
├── Makefile                           ← make dev 一键启动本地开发环境
├── run_dev.py                         ← Python 本地启动脚本（uv run uvicorn + streamlit）
├── dev_server.py                      ← Python stdlib 开发服务器（静态文件+API 代理，零依赖）
├── main.py                            ← Portal 级 FastAPI 入口（备用）
├── pyproject.toml                     ← Portal 级 Python 项目配置（uv 管理）
├── .python-version                    ← uv 指定 Python 版本
├── uv.lock                            ← uv 依赖锁定文件
├── .env.example                       ← 环境变量模板
├── .env                               ← 实际环境变量（不提交 Git）
├── .gitignore                         ← Git 忽略规则
├── .dockerignore                      ← Docker 构建忽略规则
│
├── docker-compose.yml                 ← 顶层 Docker 编排（include 子项目 + nginx 统一入口）
├── nginx/
│   └── default.conf                   ← 线上路由: / → 首页, /chatlab → HTML, /api → FastAPI, /bgm/ /photo/ 静态
│
├── static/                            ← 前端静态资源（所有页面）
│   ├── index.html                     ← 首页（Berserk 主题，Three.js 粒子，BGM 播放器）
│   ├── chatlab.html                   ← ChatLab 页面（双栏布局，左侧导入+功能，右侧预览）
│   ├── css/
│   │   ├── style.css                  ← 首页样式（深色 Berserk 主题）
│   │   └── chatlab.css                ← ChatLab 样式（纯白 + 水晶卡片阴影）
│   ├── js/
│   │   ├── main.js                    ← 首页交互（GSAP 入场动画，侧栏，BGM 播放器）
│   │   ├── chatlab.js                 ← ChatLab 交互（文件导入，API 调用，预览面板）
│   │   └── particles.js               ← Three.js 粒子背景（灰烬效果）
│   ├── bgm/
│   │   ├── Frank_Ocean_-_Self_Control.mp3
│   │   ├── Frank_Ocean_-_Pink_+_White.mp3
│   │   ├── Frank_Ocean_-_Solo.mp3
│   │   └── Frank_Ocean_-_White_Ferrari.mp3
│   └── photo/
│       └── guts.png                   ← 首页背景图（Berserk 风格）
│
├── scripts/
│   └── deploy.sh                      ← 服务器一键部署（装依赖、构建、启动、导入知识库）
│
├── .claude/
│   └── settings.local.json            ← Claude Code 项目级配置
│
└── ChatHistoryAnalyst/                ← 子项目：ChatLab
    ├── CLAUDE.md                      ← ChatLab 详细文档
    ├── README.md                      ← ChatLab 简介
    ├── pyproject.toml                 ← Python 依赖声明
    ├── .python-version                ← uv Python 版本
    ├── uv.lock                        ← uv 依赖锁
    ├── .env.example                   ← ChatLab 环境变量模板
    ├── Dockerfile                     ← 容器镜像（Python 3.12-slim）
    ├── docker-compose.yml             ← postgres + api + streamlit 三个服务
    ├── import_knowledge.py            ← 一次性脚本：data/*.txt → PGVector 知识库
    ├── src/
    │   ├── main.py                    ← FastAPI app（8 个 API 端点 + 首页/chatlab 路由 + CORS）
    │   ├── core_llm.py                ← LLM 实例（qwen3-max/base + qwen3-omni-flash/vision）
    │   ├── schemas.py                 ← Pydantic 模型（ChatMessage, AnalysisRequest, EmotionResponse 等）
    │   ├── tools.py                   ← 3 个 LangChain @tool（知识搜索、历史搜索、网页搜索）
    │   ├── rag_function.py            ← PGVector 双库管理（knowledge_store + chat_history_store）
    │   └── skills/
    │       ├── skill01_imitate.py     ← 语气模仿 Agent
    │       ├── skill02_emotion.py     ← 情感分析 Agent
    │       └── skill03_atmosphere.py  ← 气氛分析 Agent
    ├── front/
    │   └── frontend.py                ← Streamlit 前端 UI
    ├── data/
    │   ├── DBL.txt                    ← 心理学参考：辩证行为疗法
    │   ├── communication.txt          ← 沟通模式
    │   ├── deeprelation.txt           ← 深层关系心理学
    │   ├── imitate.txt                ← 语气模仿指南
    │   └── relationship.txt           ← 关系动力学
    ├── config/
    │   └── mcporter.json              ← mcporter 配置
    ├── docs/
    │   └── rag-roadmap.md             ← RAG 演进路线（HyDE, rerank, GraphRAG）
    └── .streamlit/
        └── config.toml                ← Streamlit 主题配置
```

---

## 文件职责速查

### 根目录文件

| 文件 | 职责 | 谁会在什么时候读它 |
|------|------|---------------------|
| `Makefile` | `make dev` 调 `run_dev.py` | 开发者每天本地启动 |
| `run_dev.py` | `uv run uvicorn` + `uv run streamlit` 并行启动，Ctrl+C 全停 | `make dev` 内部调用 |
| `dev_server.py` | Python stdlib HTTP server，静态文件 + `/api` 代理到 8000 | 不需要 uv 时快速开一个 dev server |
| `main.py` | Portal 级 FastAPI 入口（备用，实际用 ChatHistoryAnalyst/src/main.py） | 历史残留，可忽略 |
| `pyproject.toml` | Portal 级 Python 项目声明 | `uv sync` 时 |
| `.python-version` | 告诉 uv 用哪个 Python | `uv sync` 时 |
| `uv.lock` | 锁定所有依赖版本 | 保证环境一致 |
| `.env` / `.env.example` | 全局环境变量（API 密钥、数据库密码） | Docker Compose + 后端启动 |
| `.gitignore` | Git 忽略 `.env` `__pycache__` `.venv` 等 | 自动生效 |
| `.dockerignore` | Docker build 忽略 `.venv` `.git` `.env` 等 | `docker compose build` 时 |
| `docker-compose.yml` | include ChatHistoryAnalyst + nginx 服务 | `docker compose up` 时 |
| `TODO.md` | step-by-step 部署勾选清单 | 首次部署时 |
| `CHANGES.md` | 2026-06-04 重构变更总结 | 回顾架构决策 |
| `CONTROLWEB.md` | 服务器运维手册（买服务器→域名→HTTPS→更新→备份） | 上线和日常维护时 |
| `CLAUDE.md` | AI 辅助开发上下文 | Claude Code 自动加载 |

### static/ — 前端资源

| 文件 | 职责 |
|------|------|
| `index.html` | 首页：深色 Berserk 主题，品牌名+项目侧栏+BGM 播放器+Three.js 粒子背景 |
| `chatlab.html` | ChatLab：左 2/3（导入卡片+三个功能按钮），右 1/3（预览面板） |
| `css/style.css` | 首页暗色主题样式（Berserk · Iron & Blood） |
| `css/chatlab.css` | ChatLab 纯白主题样式（水晶卡片阴影，紧凑双栏布局） |
| `js/main.js` | 首页 JS：GSAP 入场动画、侧栏展开收起、BGM 歌单+播放+曲目显示 |
| `js/chatlab.js` | ChatLab JS：文件导入、API 调用、右侧预览渲染、分析结果弹窗 |
| `js/particles.js` | Three.js 粒子系统（灰烬飘浮背景） |
| `bgm/` | 4 首 Frank Ocean 背景音乐 |
| `photo/` | 首页背景图 `guts.png` |

### nginx/

| 文件 | 职责 |
|------|------|
| `default.conf` | 路由表：`/` 首页，`/chatlab` ChatLab 静态页，`/api` 代理 FastAPI，`/css/` `/js/` `/bgm/` `/photo/` 静态资源 |

### scripts/

| 文件 | 职责 |
|------|------|
| `deploy.sh` | 一键部署：检查 Docker → 配 `.env` → `docker compose build` → `up -d` → 导入知识库 |

### ChatHistoryAnalyst/ — ChatLab 子项目

| 文件 | 职责 |
|------|------|
| `pyproject.toml` | Python 依赖（langchain, fastapi, dashscope, pgvector, streamlit...） |
| `Dockerfile` | 容器镜像（Python 3.12-slim + 所有 pip 依赖） |
| `docker-compose.yml` | 三个容器：postgres(pgvector) + api(FastAPI) + streamlit |
| `src/main.py` | 8 个 API 端点 + 首页/chatlab 路由 + CORS + 静态挂载 |
| `src/core_llm.py` | LLM 实例（`base_llm` = qwen3-max, `vision_llm` = qwen3-omni-flash） |
| `src/schemas.py` | Pydantic 数据模型 |
| `src/tools.py` | LangChain @tool × 3（心理学检索、聊天历史检索、Tavily 网页搜索） |
| `src/rag_function.py` | PGVector 双库：knowledge_store（心理学知识）+ chat_history_store（聊天记忆） |
| `src/skills/skill01_imitate.py` | 语气模仿 Agent |
| `src/skills/skill02_emotion.py` | 情感分析 Agent（结构化 JSON 输出） |
| `src/skills/skill03_atmosphere.py` | 气氛分析 Agent（权力动态+沟通建议） |
| `front/frontend.py` | Streamlit 前端 UI（文件上传、OCR、分析卡片） |
| `data/*.txt` | 心理学参考知识文本 |
| `import_knowledge.py` | 将 `data/*.txt` 向量化导入 PGVector |
| `CLAUDE.md` | ChatLab 技术栈、架构图、开发约定 |

---

## 加新子项目范��

```
1. mkdir NewProject && 写 docker-compose.yml
2. docker-compose.yml → include 加一行
3. nginx/default.conf → 加 location 块
4. git add -A && git commit && git push
```
