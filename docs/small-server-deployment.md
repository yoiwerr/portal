# 小内存服务器构建与更新

适用：已有 Portal、共享 PostgreSQL 和 HTTPS 的单台 Linux 服务器。日常操作使用现代 `docker compose`（最低 2.20），另需 Docker Buildx、Python 3、curl 和 util-linux 的 flock。更名后还需先按 [dude 更名迁移](dude-rename.md) 检查旧目录内的忽略文件。

## 日常更新

先备份数据库和被 Git 忽略的 `.env`、Wiki 发布目录等数据，核对恢复方式。已有 `.env` 不要重新复制模板，不需要为本次构建优化新增密钥。

```bash
cd ~/portal
git status --short
git pull --ff-only
./scripts/check-production-config.sh
./scripts/update.sh dude
```

默认只构建、更新 `dude-admin` 和 `dude-api`。`journal` 只更新 Journal；`all` 更新三个应用；`nginx` 只验证和更新代理。`--rebuild`/`-f` 兼容旧调用，等于 `all`。脚本不自动拉取或合并 Git，不自动删镜像。

```bash
./scripts/update.sh journal
./scripts/update.sh nginx
# 只构建，不切换运行中的应用；不要在另一个终端同时部署
./scripts/build.sh dude-admin dude-api
# 明确确认镜像来自当前提交后，复用已构建镜像
./scripts/update.sh dude --no-build
```

应用构建失败不会开始切换应用；启动/健康检查失败会非零退出，不会继续切换 nginx 或显示成功。应用逐个启动并等待 healthy，失败时已经成功启动的应用不会自动退回旧版本，可能存在短暂混合版本。nginx 测试成功后才重建代理，HTTPS 检查验证真实证书。Go 启动执行自身迁移；Journal 更新显式运行 Alembic。数据库迁移不能靠换回旧镜像自动撤销，必须事先有备份。

已有 PostgreSQL 使用 `--no-recreate` 启动，保留容器、项目名、数据卷和数据库；若找不到已有容器则拒绝日常更新。脚本不自动停止旧名称或退役容器，需按 [下线说明](chatlab-retirement.md) 确认身份后处理。不要使用 `down -v` 或全局 `--remove-orphans`。

## 限制构建资源

所有新构建/部署入口共用 `.portal-deploy.lock` 的 flock 文件锁。进程退出后内核自动释放锁，不需要删除锁文件。手工执行原始 `docker compose build` 会绕过保护。

构建器 `portal-low-memory` 使用独立 Docker 容器，不改变默认构建器：

| 限制 | 值 |
| --- | --- |
| 内存硬上限 | 512 MiB |
| 内存加交换空间上限 | 1 GiB，实际需宿主机启用 swap |
| CPU 上限 | 0.75 个 CPU |
| 服务构建 | 逐个进行 |
| BuildKit 内部步骤 | `ops/buildkit/buildkitd.toml` 中并行度 1 |
| Go 编译 | GOMAXPROCS=1、GOFLAGS=-p=1、GOMEMLIMIT=256MiB（软目标） |
| Python 安装 | 下载并行度 2，安装/构建并行度 1，只安装 wheel |

脚本还要求至少 256 MiB 可用内存及 4 GiB 空闲磁盘；这是最低检查，不保证所有负载下都能构建。硬上限限制构建器，不能约束 Docker daemon 和现有应用，也不能消除所有 I/O/网络竞争。资源不足时宁可失败并保留当前应用。首次构建 Go 缓存会更慢。

构建器镜像固定为 `moby/buildkit:v0.20.2`，Dockerfile 前端固定为 `docker/dockerfile:1.7`。Python、Go 与应用锁文件保持现有版本，uv 固定 0.11.26。Python 导出锁定版本与哈希后，从包镜像获取 wheel 并校验哈希，避免 `uv.lock` 内的直链使安装仍去海外站点。没有兼容 wheel 时明确失败，应在开发机调查依赖，不要在小服务器临时安装整套编译器。`PYTHON_PACKAGE_INDEX` 可作为 Docker build arg 指向其他可信镜像，根 `.env` 中设置同名变量不会自动修改 build arg。

uv、Go 模块和 Go 编译结果使用 BuildKit 持久缓存。dude Python 构建上下文排除 Go 子服务、独立的 TypeScript 基础工程及 node_modules，避免上传无关依赖。新 TypeScript 服务尚未加入生产编排。

构建完成或失败后会停止构建器以释放闲置内存，保留其缓存卷。如果 Docker 不支持 swap/cgroup 限制，或同名构建器的实际限制不符，应修复后重试，不回退到无限制构建。调整资源配置时，先确认没有构建运行，再只移除专用构建器并重建：

```bash
docker buildx inspect portal-low-memory
docker buildx stop portal-low-memory
# --keep-state 保留构建器状态卷；脚本下次调用按配置重建
docker buildx rm --keep-state portal-low-memory
./scripts/build.sh dude-admin dude-api
```

## 首次安装与 Journal 账号

首次安装先填写 `.env` 并准备有效证书，运行 `./scripts/deploy.sh`。它会初始化缺失的 Journal/makeitspecific 数据库与角色，并设置这两个项目角色的密码，保留现有 alfred 数据库。**已有部署不使用首次安装入口**；缺少初始化变量会失败，不能用弱默认值绕过。

Journal 账号单独创建（已存在的同名账号会更新密码）：

```bash
docker compose run --rm --no-deps -e JOURNAL_ADMIN_USERNAME=yoiwerr \
  journal uv run --frozen --no-dev python create_user.py
```

`./scripts/deploy-journal.sh --skip-user` 仍保留单独初始化 Journal 的兼容入口，使用相同锁和受限构建器，不再顺带构建 dude-admin。省略 `--skip-user` 会交互创建或更新 Journal 账号。

## 诊断卡顿与回退

SSH 在出现密码提示前卡住，并不能证明密码错误或 OOM。先在阿里云 ECS 的 **VNC 控制台**（不依赖 SSH 的 Workbench）执行：

```bash
uptime
free -h
df -h /
ps -eo pid,ppid,comm,rss,pcpu --sort=-rss | head -n 15
docker stats --no-stream
journalctl -k --since '1 hour ago' | grep -Ei 'oom|out of memory|killed process|hung task'
journalctl -u ssh -u sshd --since '1 hour ago' --no-pager | tail -n 40
```

高 load 可能来自 CPU 或 I/O 等待；没有 OOM 日志不能声称已经发生 OOM。网络丢包、连接限制、认证钩子也可能卡住 SSH，需结合指标判断。先取消自己确认的构建任务，停止确认退役的应用；不要按端口杀进程、全局 kill、清空数据库或反复强制重启。

新脚本在覆盖镜像标签前，为当前同名服务的运行镜像保留 `portal-rollback/<service>:<UTC时间>` 标签，输出具体名称。更名前的旧容器需另存 image ID，不能假定它会被新服务名发现。回退先检查迁移兼容性，再用已记录的旧镜像更新服务；如有不兼容数据变更，按备份恢复流程操作，不能自动回退数据库。

日常脚本不做 `image prune`。缓存/旧镜像清理需要单独核对可回退版本及磁盘占用。更长期建议在 CI 或构建机生成带提交版本的镜像，让小服务器只负责拉取和运行；本轮尚未配置 CI 发布。
