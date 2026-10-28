# Alfred → dude 更名迁移

2026-10-26。本地源码已更名，本文不代表服务器已更新。

| 原名称 | 当前名称 |
| --- | --- |
| 产品 Alfred | `dude` |
| `MakeItSpecific/` | `dude/` |
| `MakeItSpecific/AlfredAdmin/` | `dude/dude-admin/` |
| Compose `specific-api` / 容器 `alfred-api` | 服务和容器均为 `dude-api` |
| Compose / 容器 `alfred-admin` | `dude-admin` |
| 主入口 `/alfred/` | `/dude/`，旧路径兼容代理 |
| Wiki `ALFRED_WIKI_*` | 优先 `DUDE_WIKI_*`，回退旧变量 |

以下兼容标识刻意保留：PostgreSQL `alfred` 库、`makeitspecific` 备用初始化库和密码变量、数据表、浏览器 `alfred_token/alfred_refresh/alfred_user`、JWT issuer `alfred-admin`。它们涉及持久化或既有客户端，不随品牌改名重建。旧 API 直接转发，保留 POST/PUT/DELETE、正文与查询参数；仅旧无尾斜杠页面入口跳转到新名称。

## 本地

本次直接移动了整个本地目录，原有忽略配置、数据和 Wiki 产物随目录保留，没有读取或改写私有内容。已有进程可能仍持有旧工作目录；先在 Portal 根目录 `make stop` 停止本启动器，再 `make dev`。

新地址为 `http://localhost:8080/dude/`。独立 Python 工具从 `dude/` 运行，Go 模块从 `dude/dude-admin/` 运行。移动过的 `.venv` 中某些直接执行的脚本可能含旧绝对路径；优先使用 `uv run --frozen python -m ...`，全新服务器用 `uv sync --frozen` 重建环境，不复制本机 `.venv`。

## 服务器：先备份，再拉代码

这是部署操作说明。从服务器 Portal 根目录执行；有本地改动先保存，不要 reset 或覆盖：

```bash
cd ~/portal
git status --short
git rev-parse HEAD
```

记录当前提交作为回滚依据。先按现有 PostgreSQL 运维文档备份 `alfred`，并在没有 Wiki 编译/发布写入时备份旧 `MakeItSpecific/var/` 和有需要的 `data/`。之后 `git pull --ff-only`。

**Git 拉取只迁移版本源码，不会迁移服务器上的忽略文件。** 根 `.env` 留在原位置，不覆盖密钥和密码。若以前在子目录维护 `.env`，需要从 `MakeItSpecific/.env` 放到 `dude/.env`；根 `.env` 已存在时仍优先使用根配置。

旧 `MakeItSpecific/var/` 必须迁入 `dude/var/`，其中包括 Wiki 原文、候选、指针与发布版本。下面仅在目标不存在时移动，遇到冲突直接停止；不删除旧目录中的其它内容：

```bash
python3 - <<'PY'
from pathlib import Path
root = Path.cwd().resolve()
pairs = [(root / 'MakeItSpecific' / name, root / 'dude' / name)
         for name in ('.env', 'var')]
for source, target in pairs:
    if source.exists() and target.exists():
        raise SystemExit(f'存在目标冲突，先比较并保留两份：{target.name}')
for source, target in pairs:
    if source.exists():
        if source.is_symlink():
            raise SystemExit(f'需要人工核对符号链接：{source.name}')
        source.rename(target)
        print(f'已迁移 {target.name}')
PY
```

若旧 `data/` 有导出、附件或日志，先备份，再将所需文件复制到新 `dude/data/`；目标有同名文件时先比较，不覆盖。`.venv`、缓存和本地 IDE/Agent 配置不应直接复制到服务器新环境。旧路径下其它个人文件须自行保留。

如果根 `.env` 配置了绝对 `ALFRED_WIKI_PUBLISHED_DIR`，变量名可继续用，但路径需手动改成新目录；推荐改用 `DUDE_WIKI_PUBLISHED_DIR`。Compose 内路径由配置固定，不读取宿主机绝对值。`DUDE_WIKI_ALLOW_SEED` 优先于旧变量；已有正式发布时建议为 false，避免漏迁发布目录后误用人工种子。

## 构建和切换

```bash
cd ~/portal
docker compose config --quiet
docker compose build dude-api dude-admin
docker compose up -d --wait --wait-timeout 120 dude-api dude-admin
docker compose exec -T dude-api curl -fsS http://localhost:8000/api/health
docker compose run --rm --no-deps nginx nginx -t
docker compose up -d --no-deps --force-recreate nginx
docker compose ps
```

重建 nginx 是为了把旧容器内载入的 upstream 切到新服务名。检查 `/dude/`、登录、聊天、管理员，以及 `/journal/` 和旧 `/alfred/`。新旧后端短时间共用原数据库，不需要创建新库或重新初始化管理员。

确认新服务健康后，核对旧容器确实属于这个 Portal Compose 项目，再停止它们：

```bash
docker inspect --format '{{.Name}} {{index .Config.Labels "com.docker.compose.project"}} {{index .Config.Labels "com.docker.compose.service"}}' alfred-api alfred-admin
# 仅在确认上述是旧 Portal 容器后执行；没有旧容器可跳过。
docker stop alfred-api alfred-admin
```

不要使用 `down -v`，也不要为了更名清空数据库或批量清理所有 orphan。旧容器可暂留作回滚准备。回滚时恢复记录的旧代码及相应旧目录的忽略配置/Wiki 备份，再构建旧服务并切回 nginx；须先保存服务器当前改动，不使用覆盖工作区的快捷命令。数据库身份未改变，无需反向迁移数据。

## 验证范围

Python 规划、Wiki、启动及代理回归、Go 权限测试和锁文件检查在本地执行。新增新旧路由和旧 Wiki 环境变量兼容测试。真实模型和业务数据库不参与更名验证；nginx/Docker 实测受本机安装条件限制，不能据静态配置检查声称服务器已部署。
