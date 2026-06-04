# Portal 重构完成 — 变更总结

> 2026-06-04

## 目标

将 ChatHistoryAnalyst 从单项目结构重构为**多项目门户架构**，实现：
- 统一首页作为入口
- 所有子项目共享一个域名和 Docker 网络
- 加新项目只需新增目录 + nginx 路由

## 新结构

```
~/portal/                                    ← 门户根目录
├── docker-compose.yml                       ← 顶层编排（include 子项目 + nginx）
├── .env.example                             ← 统一环境变量
├── .dockerignore
├── TODO.md                                  ← 部署清单
├── nginx/
│   └── default.conf                         ← 统一路由
├── static/                                  ← 首页（产品展示）
│   ├── index.html
│   └── css/style.css
├── scripts/
│   └── deploy.sh                            ← 一键部署
└── ChatHistoryAnalyst/                      ← 子项目：ChatLab
    ├── docker-compose.yml                   ← 只含 postgres + api + streamlit
    ├── Dockerfile
    ├── src/
    │   ├── main.py                          ← FastAPI (8 endpoints)
    │   ├── core_llm.py                      ← qwen3-max / qwen3-omni-flash
    │   ├── schemas.py                       ← Pydantic models
    │   ├── tools.py                         ← 3 LangChain @tools + search
    │   ├── rag_function.py                  ← PGVector 双库管理
    │   └── skills/
    │       ├── skill01_imitate.py           ← 语气模仿 Agent
    │       ├── skill02_emotion.py           ← 情感分析 Agent
    │       └── skill03_atmosphere.py        ← 气氛分析 Agent
    ├── front/
    │   └── frontend.py                      ← Streamlit UI
    ├── data/                                ← 心理学参考 .txt
    ├── import_knowledge.py                  ← 知识库导入
    └── .git/
```

## 关键设计

### Docker Compose `include` 共享网络

portal/docker-compose.yml 通过 `include` 引入子项目：

```yaml
include:
  - ChatHistoryAnalyst/docker-compose.yml

services:
  nginx:
    ...
    depends_on: [api, streamlit]
```

- 所有服务自动共享 Docker 默认网络
- nginx 用 `api:8000` / `streamlit:8501`（容器名互访）
- `docker compose up -d` 一次启动全部
- 子项目 ports 无需暴露到宿主机

### Nginx 统一路由

```
/          → static/index.html       (首页)
/chatlab   → streamlit:8501/chatlab  (ChatLab)
/api       → api:8000                (FastAPI)
```

### 首页 — 极简产品展示

- 配色：白底 + 深灰文字 + 深蓝 accent
- ChatLab 产品卡片（图标、简介、标签、按钮）
- 虚线占位卡（"更多项目即将上线"）
- 纯 HTML/CSS，零 JS 依赖，响应式

### 加新项目范式

```
1. mkdir ~/portal/NewProject
2. 写 NewProject/docker-compose.yml
3. portal/docker-compose.yml → include 加一行
4. portal/nginx/default.conf → 加 location 块
5. docker compose up -d
```

## 文件变更明细

| 操作 | 文件 | 说明 |
|------|------|------|
| 新建 | `portal/docker-compose.yml` | 顶层编排，include + nginx |
| 新建 | `portal/nginx/default.conf` | 统一路由配置 |
| 新建 | `portal/.env.example` | 环境变量模板 |
| 新建 | `portal/.dockerignore` | Docker 构建忽略 |
| 新建 | `portal/scripts/deploy.sh` | 一键部署脚本 |
| 新建 | `portal/static/index.html` | 首页 HTML |
| 新建 | `portal/static/css/style.css` | 首页样式 |
| 新建 | `portal/TODO.md` | 部署清单 |
| 修改 | `ChatHistoryAnalyst/docker-compose.yml` | 删除 nginx 服务块 |
| 修改 | `ChatHistoryAnalyst/CLAUDE.md` | 顶部注明子项目身份 |
| 删除 | `ChatHistoryAnalyst/nginx/` | 提升至 portal 层 |
| 删除 | `ChatHistoryAnalyst/static/` | 提升至 portal 层 |
| 删除 | `ChatHistoryAnalyst/scripts/` | 提升至 portal 层 |
| 删除 | `ChatHistoryAnalyst/TODO.md` | 提升至 portal 层 |

## 部署

```bash
# 将整个 ~/portal/ 目录上传到服务器
scp -r ~/portal root@<server-ip>:~/

# 服务器上执行
cd ~/portal
chmod +x scripts/deploy.sh
./scripts/deploy.sh
```

## 访问地址

| 内容 | 地址 |
|------|------|
| 首页 | `http://<IP>` |
| ChatLab | `http://<IP>/chatlab` |
| API 文档 | `http://<IP>/api/docs` |
