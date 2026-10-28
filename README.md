# Portal

dude 和 Journal 的统一入口。GitHub：[yoiwerr/portal](https://github.com/yoiwerr/portal)。

dude 原名 Alfred，源码目录已迁至 `dude/`，入口为 `/dude/`；旧 `/alfred/` 兼容。现有服务器更新前请读 [更名与忽略文件迁移](docs/dude-rename.md)。

给模型和开发者的架构入口：[AGENTS.md](AGENTS.md) → [当前项目认知](docs/project-context.md) → [全文件索引](docs/project-file-index.md)。文档描述当前工作区，不代表服务器已经同步。

dude 知识层已接入独立 LLM Wiki 编译/审阅发布流程，在线只读发布版，首次可使用明确标记的人工种子。管理命令、服务器更新、Git 不包含的产物及备份见 [LLM Wiki](dude/docs/llm-wiki.md)。

ChatLab（聊天记录分析）已独立归档并退出网站，源码目录 `ChatHistoryAnalyst/` 作为停用项目保留，默认不会启动。归档位置、旧网址行为及服务器更新步骤见 [下线说明](docs/chatlab-retirement.md)。

## 本地开发

在 Portal 根目录操作，不需要进入 `dude/`：

```bash
cd /home/yoiwerr/portal
make dev
```

前置条件：WSL/Linux、Python 3.12、uv、Go 1.22+，以及已配置的 PostgreSQL、项目数据库和模型凭证。保留现有 `.env`，只有不存在时才从 `.env.example` 创建；不要覆盖已有密钥或生产数据库密码。

启动器先构建 Go 登录服务到临时目录，再启动 dude Python（8001）、Journal（8002）、dude-admin（8083），全部就绪后提供 Portal（8080）。所有服务只监听 127.0.0.1。Python 使用锁文件安装，Go 使用只读模块模式。不启动 ChatLab/Streamlit，不占用 8000。

`make dev` 已分流登录、管理及其静态资源/API 到 Go，聊天到 Python；支持 SSE 即时转发和 dude 的 PUT/DELETE/PATCH。生产仍由 nginx 代理。完整说明与验证入口见 [本地联调](docs/local-development.md)。

根 `.env` 需要 `JWT_SECRET`（至少 32 字符）、`ADMIN_INIT_PASSWORD`、`PGSQLPASSWORD` 与实际可访问的 `DB_HOST/DB_PORT/DB_NAME/DB_USER`（兼容旧 PG_*）。Go 连接串由同一套 DB_* 自动生成，避免与 Python 连到不同库。Journal 可显式配置 `JOURNAL_DATABASE_URL`，否则用 `JOURNAL_DB_PASSWORD` 在同一实例连接 journal/journal_user；启动前需完成 Journal Alembic 迁移。启动器不会自动创建业务库或重置现有账号。

`Ctrl+C` 或另一终端的 `make stop` 停止本次启动器及其子进程组。停止前核对 PID、进程启动时间、工作目录和命令；不按端口杀进程。端口占用时报告后退出，请自行确认旧进程。`.portal-dev.lock` 是本地身份记录，已加入 Git 忽略，不能从别处复制。

之前的 `http://127.0.0.1:8767/dude/` 是使用隔离测试数据库的临时预览，不是固定开发入口，临时账号不是生产账号。

| 内容 | 本地开发 | 生产入口 |
| --- | --- | --- |
| 首页 | `http://localhost:8080/` | `https://yoiwerr.site/` |
| dude | `http://localhost:8080/dude/` | `https://yoiwerr.site/dude/` |
| Journal | `http://localhost:8080/journal/` | `https://yoiwerr.site/journal/` |
| dude 登录 | `http://localhost:8080/dude/auth/` | `https://yoiwerr.site/dude/auth/` |
| dude 管理 | `http://localhost:8080/dude/admin/` | `https://yoiwerr.site/dude/admin/` |

dude Python 文档为 `http://localhost:8001/docs`、就绪检查为 `/api/health`；Journal 就绪检查为 `http://localhost:8002/journal/health`。旧 `/chatlab` 及 ChatLab 根级 `/api` 已下线，不再代理到聊天分析服务。

## 项目与账号

- [dude](dude/README.md)：把新手的想法整理成可交给编程 Agent 实施的方案，不编写或执行代码。`dude/` 是保留的源码目录名。
- [dude-admin](dude/dude-admin/README.md)：账号、身份、模型配置和用量查询。注册始终创建普通用户；管理员可查看用户资料、角色、状态和近 30 天已记录调用及 Token。本轮不提供调整角色、封号或计费，用量不等于账单。
- Journal：个人动态与图片，使用 PostgreSQL 持久化。

管理员用户名为 `admin`，首次创建密码来自 `ADMIN_INIT_PASSWORD`。修改变量不会重置已有账号密码；不要把临时预览密码用于生产环境。

## 部署与更新

使用 Docker Compose **2.20.0 或更高版本**，从 Portal 根目录操作。共享 PostgreSQL 由根级 Compose 定义，各应用配置由子项目维护。

```bash
cd ~/portal
# 仅首次复制；已有部署保留原文件，并根据模板补齐变量
test -f .env || cp .env.example .env
vim .env
./scripts/check-production-config.sh
```

这一步只检查配置。首次部署还需要证书、数据库初始化及应用迁移；参考 [运维手册](CONTROLWEB.md)、[部署资料](docs/docker-deploy-guide.md) 和实际 Compose 配置。历史文档涉及 ChatLab 的部分已标记停用。

已有服务器应用本次下线更新时，按 [下线步骤](docs/chatlab-retirement.md#服务器更新) 操作：保留原 Compose 项目名、`chalab-postgres` 和 `pgdata` 数据卷；不要运行 `down -v` 或重新初始化数据库。停止旧 ChatLab 应用容器即可，数据库继续供 dude 和 Journal 使用。

## 目录职责

| 目录或文件 | 职责 |
| --- | --- |
| `docker-compose.yml` | 共享 PostgreSQL、nginx 与子项目编排 |
| `nginx/` | HTTPS、安全响应头和路径路由 |
| `static/` | Portal 首页和通用静态资源 |
| `Makefile`、`run_dev.py`、`dev_runtime.py` | 开发服务声明、路径代理、子进程与安全停止 |
| `dev_server.py` | 复用开发路由，只代理已运行的后端，不启动服务 |
| `dude/` | dude 源码、Python 依赖、界面及子项目配置 |
| `dude/dude-admin/` | Go 账号与管理服务 |
| `Journal/` | Journal 源码、依赖、界面、迁移及容器配置 |
| `ops/postgres/` | 数据库初始化、备份、恢复及 systemd 示例 |
| `docs/` | 运维、架构和学习资料 |
| `ChatHistoryAnalyst/` | 已停用的聊天分析源码，不参与 Portal 运行 |

依赖由各子项目分别维护，子项目不得互相导入代码。真实 `.env`、私钥、数据库导出与本地归档不提交 Git。

## 备份和验证

[PostgreSQL 备份与恢复](docs/postgresql-backup-and-restore.md) 解释每日备份、7 天保留、恢复确认与临时数据库演练。ChatLab 下线不会删除 `chatdemopg`，仍可单独备份。

本次下线路由回归（不需要数据库或在线模型）：

```bash
python3 -m unittest discover -s tests -p 'test_chatlab_retirement.py' -v
git diff --check
```

完整部署还需运行 `docker compose config --quiet`、nginx 配置检查及各服务健康检查；离线测试不代表生产服务已就绪。
