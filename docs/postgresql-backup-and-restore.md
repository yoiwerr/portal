# PostgreSQL 备份与恢复

本文针对 Portal 的单机 Docker Compose 部署。示例假定仓库位于 `/root/portal`，PostgreSQL 服务名为 `postgres`，备份目录为 `/var/backups/portal/postgres`。

## 1. `pg_dump` 和 `pg_restore` 在做什么

`pg_dump` 连接一个正在运行的 PostgreSQL 数据库，在一个一致性快照中读取表结构、数据、索引、约束等对象。备份期间应用可以继续读写；备份看到的是开始时的一致状态，不会混入一半新、一半旧的数据。

`pg_dump` 是逻辑备份，不是 PostgreSQL volume 的文件复制。它可以跨主机恢复，也通常可以恢复到同版本或更高版本的 PostgreSQL。恢复时，`pg_restore` 读取自定义格式归档并重新创建对象和导入数据。

Portal 的脚本使用：

```bash
pg_dump --format=custom --no-owner --no-privileges
```

`--no-owner --no-privileges` 让项目数据不依赖原服务器上的角色 ID 和授权记录。目标服务器仍需先创建对应数据库和应用用户。

## 2. 自定义格式与纯 SQL

自定义格式（`-Fc`）是 Portal 的默认选择：

- 文件是 PostgreSQL 归档，只能用 `pg_restore` 恢复。
- 可以先用 `pg_restore --list` 检查目录。
- 可以选择性恢复表，也支持并行恢复。
- 通常比纯 SQL 更紧凑，适合自动化备份。

纯 SQL 格式（默认或 `-Fp`）是可读 SQL 文本：

- 使用 `psql < backup.sql` 恢复。
- 容易人工查看，但不支持 `pg_restore` 的选择和并行能力。
- 大文件通常更慢，也更难精确控制恢复对象。

不要根据扩展名猜格式。Portal 生成的 `.dump` 文件应通过 `pg_restore --list` 校验。

## 3. 项目数据库、角色和图片

每个项目使用独立数据库和用户：

| 项目 | 数据库 | 应用用户 |
| --- | --- | --- |
| Journal | `journal` | `journal_user` |
| MakeItSpecific（新安装） | `makeitspecific` | `makeitspecific_user` |
| MakeItSpecific（现有线上兼容） | `alfred` | 以现有配置为准 |

不要直接重命名现有 `alfred` 数据库。应先做备份和恢复演练，再安排独立迁移窗口。

Journal 图片存储在 `journal_entry_images.data` 的 PostgreSQL `BYTEA` 字段中。单张最多 8 MB，每条动态最多 9 张，因此 `pg_dump journal` 会自动包含图片，无需额外复制上传目录。代价是图片较多时数据库、备份文件和恢复时间都会明显增加。

`pg_dump` 只备份一个数据库，不会自动备份整个集群的登录角色。灾难恢复时需要从安全位置提供数据库密码，或另行用 `pg_dumpall --globals-only` 保存角色定义。角色文件可能包含敏感的密码哈希，应按密钥材料保护。

## 4. 手动备份

先运行 Journal 备份：

```bash
cd /root/portal
sudo install -d -m 0700 /var/backups/portal/postgres
sudo ./ops/postgres/backup.sh journal
```

脚本先写入 `.partial` 临时文件，运行 `pg_restore --list` 校验后再原子改名。失败的半成品不会伪装成有效备份。

分别备份其他数据库：

```bash
sudo ./ops/postgres/backup.sh alfred
sudo ./ops/postgres/backup.sh chatdemopg
# 完成独立迁移后：
sudo ./ops/postgres/backup.sh makeitspecific
```

可用环境变量覆盖位置：

```bash
sudo PORTAL_DIR=/srv/portal BACKUP_DIR=/mnt/backup/postgres \
  ./ops/postgres/backup.sh journal
```

脚本按数据库分别清理超过 7 天的 `.dump` 文件。目录权限应限制为备份管理员可读。

## 5. 每日自动备份与 7 天保留

仓库提供 systemd service 和 timer 示例。默认每天 02:30 运行，并通过 `Persistent=true` 在服务器错过执行时间后补跑。

```bash
cd /root/portal
sudo install -m 0644 ops/postgres/portal-backup.service /etc/systemd/system/
sudo install -m 0644 ops/postgres/portal-backup.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now portal-backup.timer
systemctl list-timers portal-backup.timer
```

如果仓库路径、备份目录或 MakeItSpecific 数据库名不同，先编辑 `/etc/systemd/system/portal-backup.service` 中的 `PORTAL_DIR`、`BACKUP_DIR` 和 `ExecStart`。修改后执行：

```bash
sudo systemctl daemon-reload
sudo systemctl restart portal-backup.timer
```

手动试跑并查看日志：

```bash
sudo systemctl start portal-backup.service
sudo systemctl status portal-backup.service
journalctl -u portal-backup.service --since today
```

## 6. 如何校验备份

目录校验能发现格式错误和明显截断：

```bash
cd /root/portal
docker compose exec -T postgres pg_restore --list \
  < /var/backups/portal/postgres/journal-YYYYmmddTHHMMSSZ.dump
```

同时记录并定期检查文件大小和哈希：

```bash
sha256sum /var/backups/portal/postgres/journal-*.dump
```

哈希只能证明文件后来没有变化，不能证明内容能完整恢复。可靠校验必须包含恢复演练。

## 7. 在临时数据库做恢复演练

不要第一次就在生产数据库上测试恢复。先创建隔离的临时数据库：

```bash
cd /root/portal
docker compose exec -T postgres createdb -U postgres journal_restore_test
docker compose exec -T postgres pg_restore -U postgres \
  --no-owner --no-privileges --dbname=journal_restore_test \
  < /var/backups/portal/postgres/journal-YYYYmmddTHHMMSSZ.dump
```

检查表、迁移版本和关键数据：

```bash
docker compose exec -T postgres psql -U postgres -d journal_restore_test \
  -c '\\dt journal_*'
docker compose exec -T postgres psql -U postgres -d journal_restore_test \
  -c 'select * from alembic_version;'
docker compose exec -T postgres psql -U postgres -d journal_restore_test \
  -c 'select count(*) from journal_entries;'
docker compose exec -T postgres psql -U postgres -d journal_restore_test \
  -c 'select count(*), coalesce(sum(size_bytes), 0) from journal_entry_images;'
```

更完整的演练应让临时 Journal 实例连接该数据库，验证登录、动态列表、创建/编辑/删除，以及至少打开一张 `/journal/api/images/{id}` 图片。最后再删除临时数据库：

```bash
docker compose exec -T postgres dropdb -U postgres journal_restore_test
```

## 8. 生产恢复步骤

恢复会覆盖目标数据库，先安排维护窗口并再做一份当前状态备份。

1. 停止写入目标数据库的应用容器。
2. 核对目标数据库名和备份文件绝对路径。
3. 用 `pg_restore --list` 校验归档。
4. 运行仓库恢复脚本。
5. 运行 Alembic 并启动应用。
6. 验证健康检查、登录、CRUD 和图片读取。

```bash
cd /root/portal
docker compose stop journal
sudo ./ops/postgres/backup.sh journal
sudo ./ops/postgres/restore.sh journal \
  /var/backups/portal/postgres/journal-YYYYmmddTHHMMSSZ.dump
# 按提示完整输入：RESTORE journal
docker compose run --rm journal uv run alembic upgrade head
docker compose up -d journal nginx
docker compose ps
docker compose logs --tail=100 journal
```

`restore.sh` 只允许已知项目数据库，并要求明确输入 `RESTORE <database>`。它使用 `--clean --if-exists` 删除归档内已有对象后恢复，所以不能在仍有业务写入时运行。

## 9. 常见错误

- `role ... does not exist`：先用初始化脚本创建应用角色，或保持 `--no-owner --no-privileges`。
- `database ... does not exist`：先幂等初始化目标数据库。
- `permission denied`：检查执行恢复的数据库管理员和目标数据库 owner。
- `unsupported version in file header`：目标 `pg_restore` 太旧；使用与源端相同或更新的 PostgreSQL 客户端。
- `relation already exists`：目标库非空且恢复时未使用清理选项；生产恢复应使用仓库脚本。
- Alembic 版本不一致：确认代码提交和备份时间匹配，再运行 `alembic upgrade head`。
- 动态存在但图片打不开：检查 `journal_entry_images` 行数和 `BYTEA` 数据是否恢复，并确认 nginx 请求体限制及应用日志。

## 10. RPO、RTO 与异地备份

RPO（恢复点目标）表示最多能接受丢失多长时间的数据。每日一次备份的理论 RPO 接近 24 小时。

RTO（恢复时间目标）表示从事故发生到业务恢复需要多久。数据库大小、下载备份、恢复速度、迁移和验证都会影响 RTO。

本机备份不等于异地备份。同一块磁盘、同一台服务器上的 dump 无法抵御磁盘损坏、误删、勒索软件或整机故障。应把备份加密复制到另一台主机或对象存储，并监控复制失败。

没有验证过恢复的备份不能算可靠备份。至少每月做一次临时数据库恢复演练，记录耗时、校验结果和失败处理，才能知道实际 RPO/RTO 是否满足要求。
