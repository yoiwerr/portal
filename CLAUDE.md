# Portal — AI 工具集入口

> 多项目统一入口。GitHub: [yoiwerr/portal](https://github.com/yoiwerr/portal)

## 架构

```
~/portal/                          ← Git 仓库根目录
│
├── Makefile                       ← make dev 本地一键启动
├── docker-compose.yml             ← Docker 编排（include 子项目 + nginx 统一入口）
├── .env.example                   ← 环境变量模板
├── .gitignore
│
├── nginx/default.conf             ← 线上路由: / → 首页, /chatlab → Streamlit, /api → FastAPI
├── static/                        ← 首页 (纯 HTML/CSS)
│   ├── index.html
│   └── css/style.css
├── scripts/deploy.sh              ← 服务器一键部署
├── TODO.md                        ← 部署清单
│
└── ChatHistoryAnalyst/            ← 子项目: ChatLab
    ├── pyproject.toml             ← Python 项目标识
    ├── src/     FastAPI 后端 (8 个 API 端点 + 3 个 Skill Agent)
    ├── front/   Streamlit 前端
    ├── data/    心理学参考 .txt
    ├── docker-compose.yml         ← postgres + api + streamlit
    └── CLAUDE.md                  ← ChatLab 详细文档
```

**两层职责:**

| 层 | 职责 | 改什么 |
|----|------|--------|
| portal/ | Docker 编排、nginx 路由、部署脚本 | 上新项目、改路由 |
| ChatHistoryAnalyst/ | 业务代码、Python 依赖 | 写功能、修 bug |

## 本地开发

```bash
cd ~/portal
make dev
```

拉起 FastAPI (:8000) + Streamlit (:8501)，`Ctrl+C` 全停。

打开 `http://localhost:8000` → 首页 → 点 ChatLab → 跳到 :8501。

- FastAPI `/` → `static/index.html`
- FastAPI `/chatlab` → 302 重定向到 `localhost:8501`
- Streamlit 直连 `localhost:8000/api/v1/*`

## 服务器部署

```bash
git clone https://github.com/yoiwerr/portal.git ~/portal
cd ~/portal
cp .env.example .env && vim .env   # 填入密钥，DB_HOST=postgres
chmod +x scripts/deploy.sh && ./scripts/deploy.sh
```

访问 `http://<公网IP>`。nginx 层路由: `/` 首页, `/chatlab` Streamlit, `/api` FastAPI。

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
