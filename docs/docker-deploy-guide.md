# Docker 部署学习笔记

> 面向实际运维，不是 Docker 说明书。每个概念都配 Portal 项目的真实例子。

---

## 1. 为什么用 Docker

把"在我电脑上能跑"变成"随便哪台服务器都能跑"。Docker 把代码、依赖、Python 版本、系统库全部打包成一个镜像，服务器只要装了 Docker 就能启动，不用管 Python 装了没、版本对不对。

Portal 项目涉及：Python 3.12、PostgreSQL + pgvector、nginx、uvicorn、Streamlit、200+ Python 包。没有 Docker 的话，服务器上要手动装所有这些。有了 Docker 就一条命令部署。

---

## 2. 核心概念（用 Portal 例子说人话）

### 2.1 镜像 vs 容器

| 概念 | 类比 | Portal 例子 |
|------|------|-------------|
| **镜像** | 安装包 / `.exe` | `Dockerfile` 跑完生成的东西，包含了 Python 3.12 + 所有 pip 包 + Alfred 源码 |
| **容器** | 正在运行的程序 | `docker compose up -d` 后跑起来的 alfred-api、chalab-api |

同一个镜像可以起多个容器。改代码需要重新 `docker compose build` 生成新镜像，然后起新容器。

### 2.2 docker-compose.yml

单容器够简单，但 Portal 有 5 个服务（nginx、api、streamlit、specific-api、postgres），手动一个个启太累。

`docker-compose.yml` 就是一个说明书：告诉 Docker 这些服务叫什么、用哪个镜像、开放哪个端口、依赖谁先启动。`docker compose up -d` 一键全起。

Portal 的 compose 特殊之处：用了 `include` 把子项目的 compose 文件引入，这样 Alfred 和 ChatLab 各管各的 Docker 配置，portal 层只负责编排 + nginx。

### 2.3 Volume — 数据持久化

容器重启后文件系统全部重置。数据库不能每次丢，所以用 volume 把 PG 数据目录映射到宿主机磁盘：

```yaml
volumes:
  - pgdata:/var/lib/postgresql/data   # 数据存在宿主机，容器删了数据还在
```

### 2.4 Network — 容器间通信

所有 compose 服务自动在同一个虚拟网络里。容器之间用 **服务名** 当主机名互相访问：

```
specific-api 容器 → 连接 postgres:5432   # 不是 localhost，是 compose 服务名
nginx 容器      → 反向代理 api:8000       # 同理
```

本地开发时连 `localhost:5432`，Docker 里连 `postgres:5432`。这就是为什么 `.env` 里 `DB_HOST` 在服务器上要写 `postgres` 而不是 `localhost`。

---

## 3. Portal 项目 Docker 架构

```
┌────────────────────────────────────────────┐
│           docker compose (portal)          │
│                                            │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐ │
│  │  nginx   │  │ chalab-  │  │  alfred-  │ │
│  │ :80 :443 │  │ api  :80 │  │ api   :80 │ │
│  │  alpine  │  │ python3. │  │ python3. │ │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘ │
│       │             │             │       │
│       └─────────────┼─────────────┘       │
│                     │                     │
│              ┌──────┴──────┐              │
│              │  postgres   │              │
│              │  :5432      │              │
│              │  pgvector   │              │
│              │  pg16       │              │
│              └─────────────┘              │
│                                            │
│  include:                                  │
│    ChatHistoryAnalyst/docker-compose.yml   │
│    MakeItSpecific/docker-compose.yml       │
└────────────────────────────────────────────┘
```

| 容器 | 镜像来源 | 端口 | 干什么 |
|------|----------|------|--------|
| `portal-nginx` | nginx:alpine（官方） | 80, 443 | 入口，路由分发 |
| `chalab-postgres` | pgvector/pgvector:pg16 | 5432（内网） | 共享 PostgreSQL，两个独立库 |
| `chalab-api` | ChatHistoryAnalyst/Dockerfile | 8000（内网） | ChatLab FastAPI 后端 |
| `chalab-streamlit` | ChatHistoryAnalyst/Dockerfile | 8501（内网） | ChatLab Streamlit 前端 |
| `alfred-api` | MakeItSpecific/Dockerfile | 8000（内网） | Alfred Agent 后端 |

---

## 4. 数据库结构

同一个 PostgreSQL 实例，两个独立数据库：

```
postgres:5432
├── chatdemopg    ← ChatLab（聊天分析 + 心理学知识库 + LLM 记忆）
└── alfred        ← Alfred（任务契约 + 知识库 chunks + 会话记忆 + 用户画像）
```

- `PGSQLPASSWORD` 一个密码管两个库
- `init-scripts/01-create-alfred-db.sql` 在 PG 容器**首次启动**时自动执行 `CREATE DATABASE alfred`
- 表（4 张向量表 + 3 张知识图谱表 + sessions/messages/feedback/contracts）由各服务启动时自动建，无需手动操作

---

## 5. 常用命令速查

```bash
cd ~/portal

# ── 启动 & 停止 ──
docker compose up -d                    # 启动（不重建镜像）
docker compose up -d --build            # 重建镜像并启动
docker compose down                     # 停止并删除所有容器
docker compose restart specific-api     # 单独重启 Alfred

# ── 查看状态 ──
docker compose ps                       # 所有容器运行状态
docker compose logs --tail=50 specific-api    # Alfred 最近 50 行日志
docker compose logs -f specific-api           # Alfred 实时日志
docker stats                            # CPU / 内存占用

# ── 进入容器调试 ──
docker compose exec specific-api bash         # 进 Alfred 容器
docker compose exec postgres psql -U postgres -d alfred   # 进 Alfred 数据库

# ── 重建（改了代码/依赖后）──
docker compose build --no-cache specific-api  # 强制重建（不用缓存）
docker compose up -d --force-recreate specific-api  # 用新镜像重建容器
```

---

## 6. 首次在服务器部署

```bash
# 1. 安装 Docker
curl -fsSL https://get.docker.com | sudo bash
sudo usermod -aG docker $USER
# 退出重新登录让权限生效

# 2. 安装 docker compose 插件
sudo apt update && sudo apt install docker-compose-plugin -y

# 3. 拉代码 + 配环境变量
git clone git@github.com:yoiwerr/portal.git ~/portal
cd ~/portal
vim .env    # 填入密钥

# 4. 一键部署
chmod +x scripts/deploy.sh
./scripts/deploy.sh
```

`deploy.sh` 做的事情：
1. 检查 Docker 是否安装
2. `.env` 不存在则交互式创建
3. `docker compose build` 构建所有镜像（第一次较慢）
4. `docker compose up -d` 启动所有服务
5. 轮询 health check 等全部就绪
6. 打印访问地址

---

## 7. 日常更新代码

```bash
cd ~/portal
git pull origin master
docker compose up -d --build     # 有依赖变更时
# 或
docker compose up -d             # 只改了源码没改依赖时
```

`scripts/update.sh` 会自动检测哪些子项目有代码变更，只重建需要重建的镜像，比全量 rebuild 快一大截。

### 什么时候需要 `--build`

| 改了什么 | 需要 `--build`？ |
|----------|------------------|
| Python 源码（.py） | ❌ 不需要，restart 就行 |
| `pyproject.toml` 加/改依赖 | ✅ 需要 |
| `Dockerfile` | ✅ 需要 |
| nginx 配置 | ❌ 不需要，restart nginx 就行 |
| `.env` 环境变量 | ❌ 不需要，restart 容器就行 |
| 前端 HTML/CSS/JS | ❌ 不需要（挂载的 volume 自动同步） |

---

## 8. 故障排查

### 8.1 容器起不来

```bash
docker compose ps          # 看哪些是 "Up"，哪些是 "Exited"
docker compose logs api    # 看那个容器的错误日志
```

常见原因：
- `.env` 里 `PGSQLPASSWORD` 跟 PG 容器初始化时的不一致 → 删掉 volume 重建
- `DEEPSEEK_API_KEY` 格式不对 → Alfred 启动报 LLM 连接失败
- 端口被占用 → `sudo lsof -i :80` 看谁占了

### 8.2 502 Bad Gateway

nginx 能跑但连不上后端。排查链：

```bash
# 1. 后端容器活着吗
docker compose ps | grep -E "api|specific-api"

# 2. 后端在自己端口上能响应吗
docker compose exec specific-api curl -sf http://localhost:8000/api/health

# 3. nginx 能连上后端吗（从 nginx 容器内测试）
docker compose exec nginx wget -qO- http://specific-api:8000/api/health
```

常见原因：后端容器 crash 了（查 `docker compose logs`）、容器启动了但 health check 没过（nginx 等它 healthy 才放流量）。

### 8.3 数据库连不上

```bash
# 纯 PG 层检查
docker compose exec postgres pg_isready -U postgres
docker compose exec postgres psql -U postgres -c "\l"   # 列出所有数据库
docker compose exec postgres psql -U postgres -d alfred -c "\dt"  # 列出 alfred 的表
```

常见原因：
- 容器内 `DB_HOST` 写了 `localhost` → 应该是 `postgres`（Docker 内网用 compose 服务名）
- `PGSQLPASSWORD` 跟 PG 容器初始化密码不一致
- 数据库不存在 → 手动 `CREATE DATABASE alfred`

### 8.4 SSL 证书过期

```bash
sudo certbot certificates                              # 看证书状态
sudo certbot renew --dry-run                           # 模拟续期（先试）
sudo certbot renew --quiet --deploy-hook "docker compose restart nginx"  # 正式续期
```

---

## 9. 数据备份 & 恢复

```bash
cd ~/portal

# 备份
DATE=$(date +%Y%m%d)
docker compose exec postgres pg_dump -U postgres chatdemopg > backup_chatlab_$DATE.sql
docker compose exec postgres pg_dump -U postgres alfred     > backup_alfred_$DATE.sql

# 恢复到当前实例
docker compose exec -T postgres psql -U postgres chatdemopg < backup_chatlab_20260726.sql
docker compose exec -T postgres psql -U postgres alfred     < backup_alfred_20260726.sql

# 备份到本地（在本地电脑执行）
scp root@<服务器IP>:~/portal/backup_*.sql .
```

建议配个 crontab 自动备份：

```bash
crontab -e
# 加一行：每天凌晨 2 点备份
0 2 * * * cd ~/portal && docker compose exec postgres pg_dump -U postgres chatdemopg > backup_chatlab_$(date +\%Y\%m\%d).sql && docker compose exec postgres pg_dump -U postgres alfred > backup_alfred_$(date +\%Y\%m\%d).sql
```

---

## 10. 空间清理

Docker 会堆积旧镜像和构建缓存，长期不清理能吃掉几十 GB。

```bash
docker system df                    # 总览：镜像、容器、volume 各占多少
docker image prune -a               # 删除所有未使用的镜像
docker builder prune                # 删除构建缓存
docker volume prune                 # 删除未使用的 volume（⚠ 会丢数据！先确认）
docker system prune -a --volumes    # 大扫除（⚠ 删所有未使用的东西）
```

安全清理（保留最近 24h 的）：

```bash
docker image prune -f --filter "until=24h"
```

---

## 11. Dockerfile 是怎么写的

以 Alfred 的 Dockerfile 为例，逐行解释：

```dockerfile
FROM python:3.12-slim          # 基于 Python 3.12 官方精简镜像

WORKDIR /app                    # 容器内工作目录，后面所有路径以此为基准

# 换阿里云 apt 源（国内提速）+ 装 gcc + libpq-dev（psycopg 需要）+ curl（healthcheck）
RUN sed -i 's/deb.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list.d/debian.sources \
    && apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

# 装 uv（比 pip 快很多的包管理器）
RUN pip install --no-cache-dir -i https://mirrors.aliyun.com/pypi/simple/ uv

# 先只复制依赖声明文件（利用 Docker 层缓存：如果 pyproject.toml 没变，这层就不重跑）
COPY pyproject.toml ./

# 装依赖
RUN uv pip install --system --no-cache-dir \
    -i https://mirrors.aliyun.com/pypi/simple/ \
    fastapi 'uvicorn[standard]' sse-starlette httpx pydantic python-dotenv \
    dashscope langchain langchain-community langchain-openai langgraph \
    psycopg pgvector aiohttp numpy python-multipart

# 最后复制源代码（这层经常变，放最后避免前面的层缓存失效）
COPY . .
```

关键思路：**变的东西放最后，不变的放前面**。`pyproject.toml` 比源码变动少得多，所以先 COPY + RUN install，这样改一行代码不需要重新下载所有包。

---

## 12. Docker Compose 关键字段解释

```yaml
services:
  specific-api:                              # 服务名 — 也是容器间通信的主机名
    build: .                                  # 用当前目录的 Dockerfile 构建
    container_name: alfred-api               # 固定的容器名（方便 docker logs 指定）
    command: uvicorn app:app --host 0.0.0.0 --port 8000   # 容器启动时执行的命令
    environment:                              # 注入环境变量，${VAR} 从宿主机 .env 读
      DEEPSEEK_API_KEY: ${DEEPSEEK_API_KEY}
    depends_on:                               # 启动顺序
      postgres:
        condition: service_healthy            # 等 postgres health check 通过才启动
    restart: unless-stopped                   # 除非手动 stop，否则挂了自动重启
    mem_limit: 1g                             # 最多用 1G 内存
    healthcheck:                              # 怎么能判断这个服务是健康的
      test: ["CMD-SHELL", "curl -f http://localhost:8000/api/health || exit 1"]
      interval: 30s                           # 每 30 秒检查一次
      timeout: 10s                            # 单次检查超时 10 秒
      retries: 3                              # 连续 3 次失败 = unhealthy
      start_period: 30s                       # 启动后给 30 秒预热时间
```

---

## 13. 本地开发 vs Docker 部署的关键差异

| 场景 | 本地 `make dev` | Docker 部署 |
|------|----------------|-------------|
| Python | 系统 Python 3.12 + uv venv | 容器内 Python 3.12-slim |
| PostgreSQL | `localhost:5432`，手动建库 | `postgres:5432`（compose 服务名），init-scripts 自动建库 |
| 包管理 | `uv run` 自动读 `pyproject.toml` | Dockerfile 里 `uv pip install` 固定包列表 |
| nginx | `run_dev.py` 内置 Python HTTP server | nginx:alpine 容器 |
| 热重载 | uvicorn `--reload` | 无，改代码需重启容器 |
| 多服务 | Python subprocess 管理 | Docker compose 编排 |

本地开发和 Docker 部署 **共用同一份源码**，但运行方式完全不同。本地改代码即时生效，Docker 需要 rebuild 或 restart。

---

## 14. 加新子项目的 Docker 范式

假设要加一个 `PhotoGallery` 项目：

```
1. mkdir PhotoGallery
2. 写 PhotoGallery/Dockerfile         ← 怎么构建镜像
3. 写 PhotoGallery/docker-compose.yml   ← 定义服务（不用写 postgres，复用 ChatLab 的）
4. portal/docker-compose.yml → include 加一行 PhotoGallery/docker-compose.yml
5. portal/nginx/default.conf → 加 location /gallery { proxy_pass ... }
6. portal/init-scripts/ → 如需新数据库加一个 .sql
7. git add -A && git commit && git push
8. 服务器 docker compose up -d --build
```

---

## 15. 关键教训（从实际踩坑记录）

1. **`--build` 很慢，不需要每次都加。** 只改 Python 代码直接 `docker compose up -d` + `restart`。

2. **环境变量 `DB_HOST` 在 Docker 里必须写 compose 服务名不是 localhost。** 写了 `localhost` 容器只会连自己，找不到 PG。

3. **PG 容器首次启动时用 `init-scripts/` 建库，已运行的不会自动补建。** 升级时如果加了新数据库，需要手动 `CREATE DATABASE`。

4. **`.env` 改了 key 后要重建容器**（环境变量在容器启动时注入，不 restart 不生效）。

5. **国内服务器配阿里云镜像源**（apt + pip），不配的话下载速度可能只有几十 KB/s。

6. **nginx 的 `depends_on` 用 `service_healthy` 而不是 `service_started`。** start 了不代表健康，nginx 会在后端没准备好时返回 502。

7. **docker compose 的 `include` 路径相对于被 include 文件的目录。** MakeItSpecific/docker-compose.yml 里的 `build: .` 是 MakeItSpecific 目录，不是 portal 根目录。


## 已有 Portal 服务器加入 Journal（Git 拉取部署）

以下步骤适用于服务器已经运行旧版 Portal、且必须保留现有 PostgreSQL volume 的情况。

1. 在本地提交本次代码后推送：

```bash
git add Journal ops scripts/check-production-config.sh scripts/deploy-journal.sh \
  docs/postgresql-backup-and-restore.md docs/docker-deploy-guide.md \
  .env.example docker-compose.yml nginx/default.conf run_dev.py \
  MakeItSpecific/pyproject.toml MakeItSpecific/uv.lock MakeItSpecific/AlfredAdmin/
git commit -m "deploy portal journal with postgres"
git push
```

不要提交 `.env`、`Journal/data/`、`Journal/.venv/`、TLS 私钥或任何真实密码。它们被 `.gitignore` 排除，必须留在服务器或通过安全的密钥管理方式注入。

2. 登录服务器并进入现有项目目录：

```bash
cd ~/portal
git status --short
git pull --ff-only
cp .env.example .env   # 仅首次；已有 .env 不要覆盖
chmod 600 .env
```

3. 编辑 `.env`，至少填写 `PGSQLPASSWORD`（现有 PostgreSQL 管理密码）、`JOURNAL_DB_PASSWORD`、`JWT_SECRET`、`ADMIN_INIT_PASSWORD` 以及已有 LLM 密钥。不要把这些值提交到 Git。

4. 确认证书路径仍然存在，然后运行：

```bash
./scripts/deploy-journal.sh
```

脚本不会删除 volume、不会重命名已有数据库，也不会执行 `docker compose down -v`；它只幂等创建 `journal_user` 和 `journal`，运行 Journal Alembic，构建并启动 Journal，再重载 nginx。

5. 如果只想先迁移和启动、不创建用户：

```bash
./scripts/deploy-journal.sh --skip-user
```

之后创建用户：

```bash
docker compose run --rm -e JOURNAL_ADMIN_USERNAME=yoiwerr journal uv run python create_user.py
```

6. 验证：

```bash
docker compose ps
docker compose logs --tail=100 journal
curl --fail --silent --show-error --insecure \
  --resolve yoiwerr.site:443:127.0.0.1 \
  https://yoiwerr.site/journal/health
```

7. 启用每日备份：

```bash
sudo install -m 0644 ops/postgres/portal-backup.service /etc/systemd/system/
sudo install -m 0644 ops/postgres/portal-backup.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now portal-backup.timer
systemctl list-timers portal-backup.timer
```

备份脚本需要 `PGPASSWORD` 和 `BACKUP_DIR` 等环境变量，当前容器内备份方案不需要数据库密码文件；systemd 示例默认项目位于 `/home/yoiwerr/portal`。如果服务器路径不同，安装 service 前修改 `PORTAL_DIR` 和 `ExecStart`。

### Git 拉取后必须手动放入服务器的文件

- `~/portal/.env`：生产密码、JWT、LLM 密钥和 Journal 数据库密码。
- `/etc/letsencrypt/live/yoiwerr.site/{fullchain.pem,privkey.pem}`：TLS 证书（如果服务器已有则无需重新放置）。

不需要手动放入的文件：Journal 源码、迁移、Dockerfile、脚本和文档都会由 Git 拉取；`Journal/data/` 和 `.venv/` 是本地运行产物，不应复制到生产。
