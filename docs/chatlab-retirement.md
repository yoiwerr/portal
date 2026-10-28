# ChatLab 独立归档与网站下线

## 保存了什么

本地 WSL 完整快照位于：

```text
/home/yoiwerr/project-archives/chatlab-20261020.wP6nKm/
  chatlab-portal-snapshot.tar.gz
  SHA256SUMS
```

快照包含 `ChatHistoryAnalyst/` 的完整文件（包括本地环境和数据文件）、原 ChatLab HTML/CSS/JS、原根级 Compose/开发启动器/部署脚本、初始化 SQL 和环境模板。该目录在 Portal 仓库外，权限限制为当前用户访问，**不随 Git 推送到服务器**。不要公开归档，本地环境或项目文件可能包含私有信息。

归档已通过 gzip 完整性检查、tar 目录读取和 SHA-256 生成。仓库中的 `ChatHistoryAnalyst/` 源码也保留，退出默认启动及部署；尚未创建独立远程仓库。历史子项目 Compose 包含共享 PostgreSQL，不能直接在现有 Portal 项目中再次启动。

这是文件快照，**不包含 PostgreSQL 在线数据导出**。旧 `chatdemopg` 数据库保留，本机无法运行 Docker 时未执行数据库备份。服务器下线前应单独执行：

```bash
cd ~/portal
./ops/postgres/backup.sh chatdemopg
```

已有根级 `.env` 原样保留，没有复制到归档或提交 Git；恢复时需另行安全配置实际凭证。

## 改动范围

- 首页仅移除 ChatLab 卡片，dude 与 Journal 入口保留。
- 删除公开目录内的 `static/chatlab.html`、`static/css/chatlab.css`、`static/js/chatlab.js`；可从快照恢复。
- nginx 对 `/chatlab*`、旧静态资源及根级 `/api*` 返回 410，不再连接 `api:8000`。dude 使用 `/dude/api/`，Journal 使用 `/journal/`，保持原路由。
- 开发启动器不再运行 ChatLab、不检查 8000 端口；保留 dude 已有根级 API 开发别名，其他原 ChatLab API 返回 410。回归时发现 dude 开发代理会丢失查询参数，已修复，保证 `?v=2` 等参数传递。
- 根级 Compose 不再包含 ChatLab 的 `api` 和 `streamlit`。PostgreSQL 定义从子项目移到根级，保留 `postgres` 服务名、`chalab-postgres` 容器名、`pgdata` 卷、镜像、初始化目录及原 `chatdemopg` 健康检查。
- `chatdemopg` 是历史数据库名，不代表重新启用 ChatLab。没有重命名数据库、删除表、清空卷或更改已有密码。
- 部署与更新脚本移除 ChatLab 的构建、等待、知识库导入和健康检查；更新 dude 时同时更新 Go 账号服务。

## 服务器更新

以下命令在本次代码提交、推送后执行；本地修改不会自动更新服务器。

1. 在原 `~/portal` 目录、使用原 Compose 项目名操作。若以前设置了 `COMPOSE_PROJECT_NAME` 或 `-p`，必须沿用。先查看实际 PostgreSQL 卷名称和挂载，记录结果并备份：

   ```bash
   cd ~/portal
   git status --short
   docker inspect chalab-postgres --format '{{json .Mounts}}'
   ./ops/postgres/backup.sh chatdemopg
   ./ops/postgres/backup.sh alfred
   ./ops/postgres/backup.sh journal
   ```

2. 保留服务器现有 `.env`，拉取代码、验证配置。预期服务只有 `postgres`、`dude-api`、`dude-admin`、`journal`、`nginx`：

   ```bash
   git pull --ff-only origin master
   ./scripts/check-production-config.sh
   docker compose config --services
   docker compose ps postgres
   ```

3. 更新应用，然后检查和更新 nginx。此处用 `--no-deps` 保留正在运行的共享数据库，不因编排文件位置变化而重建它：

   ```bash
   docker compose up -d --build --no-deps --wait --wait-timeout 120 dude-admin dude-api journal
   docker compose run --rm --no-deps nginx nginx -t
   docker compose up -d --no-deps --force-recreate nginx
   ```

4. 检查旧 ChatLab 容器名称及所属项目，确认确实是此 Portal 的旧应用后停止。保留停止的容器方便回退，**不要停止 `chalab-postgres`**：

   ```bash
   docker ps -a --filter name=chalab-api --filter name=chalab-streamlit
   docker inspect chalab-api chalab-streamlit --format '{{.Name}} {{index .Config.Labels "com.docker.compose.project"}} {{index .Config.Labels "com.docker.compose.service"}}'
   docker stop chalab-api chalab-streamlit
   ```

   如果旧容器不存在，跳过这一步。不要使用全局容器清理或 `docker compose down -v`。

5. 验证入口和旧 URL（以下输出应依次为 200、200、200、410、410；登录页应能打开，认证与 CRUD 另按正常流程验证）：

   ```bash
   docker compose ps
   curl -sS -o /dev/null -w '%{http_code}\n' https://yoiwerr.site/
   curl -sS -o /dev/null -w '%{http_code}\n' https://yoiwerr.site/dude/auth/
   curl -sS -o /dev/null -w '%{http_code}\n' https://yoiwerr.site/journal/health
   curl -sS -o /dev/null -w '%{http_code}\n' https://yoiwerr.site/chatlab
   curl -sS -o /dev/null -w '%{http_code}\n' https://yoiwerr.site/api/v1/imported_files
   ```

没有新增必填密钥。现有 Tavily、LangSmith 等 ChatLab 配置不再被根级部署使用，可留在服务器 `.env` 中，避免误删其他用途的凭证。

## 校验和恢复文件

先校验，再解压到新目录，避免覆盖现在的 Portal：

```bash
cd /home/yoiwerr/project-archives/chatlab-20261020.wP6nKm
sha256sum -c SHA256SUMS
gzip -t chatlab-portal-snapshot.tar.gz
task_restore=$(mktemp -d /home/yoiwerr/chatlab-restore.XXXXXX)
tar -xzf chatlab-portal-snapshot.tar.gz -C "$task_restore"
printf '%s\n' "$task_restore"
```

完整文件快照与原 Compose 已保存，但它仍沿用原 Portal 相对目录约定。将其作为独立项目启动前，要单独设置 Compose 项目名、端口、数据库凭证及静态资源路由，防止连接或重建现有 Portal 数据库；跨路径使用时应重新建立 uv 虚拟环境。数据库恢复另按 [备份恢复文档](postgresql-backup-and-restore.md) 操作，文件解压本身不会恢复数据库。
