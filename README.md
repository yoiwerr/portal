# Portal

AI 工具集统一入口。

## 启动

### 本地开发

```bash
cd ~/portal
make dev
```

拉起 FastAPI (:8000) + Streamlit (:8501)，`Ctrl+C` 全停。

打开 `http://localhost:8000` → 首页 → 点 ChatLab → 跳到 :8501。

### 服务器部署

```bash
git clone https://github.com/yoiwerr/portal.git ~/portal
cd ~/portal
cp .env.example .env && vim .env   # 填入密钥，DB_HOST=postgres
chmod +x scripts/deploy.sh && ./scripts/deploy.sh
```

访问 `http://<公网IP>`。

## 目录

```
portal/
├── Makefile                  make dev 一键启动
├── docker-compose.yml        Docker 编排，include 子项目 + nginx
├── .env.example              环境变量模板
│
├── nginx/                    线上 nginx 配置
│   └── default.conf          路由: / → 首页, /chatlab → Streamlit, /api → FastAPI
│
├── static/                   首页 (纯 HTML/CSS/JS)
│   ├── index.html            入口页面
│   ├── chatlab.html          旧版 ChatLab 静态页
│   ├── css/                  样式
│   ├── js/                   脚本
│   ├── bgm/                  背景音乐
│   └── photo/                图片
│
├── scripts/                  运维脚本
│   └── deploy.sh             服务器一键部署
│
├── ChatHistoryAnalyst/       子项目：ChatLab
│   ├── pyproject.toml        Python 项目依赖
│   ├── src/                  FastAPI 后端 (API 端点 + Skill Agent)
│   ├── front/                Streamlit 前端
│   ├── data/                 心理学参考数据
│   ├── config/               配置文件
│   ├── docker-compose.yml    postgres + api + streamlit
│   ├── Dockerfile            容器镜像
│   └── CLAUDE.md             ChatLab 详细文档
│
├── run_dev.py                本地开发启动脚本
├── dev_server.py             开发服务器辅助
├── TODO.md                   部署清单
└── CHANGES.md                变更记录
```
