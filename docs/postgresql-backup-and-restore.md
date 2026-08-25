# PostgreSQL 备份与恢复

`pg_dump` 在单个一致性快照中读取数据库对象和数据；自定义格式（`-Fc`）由 `pg_restore` 选择性恢复，纯 SQL（`-Fp`）可直接交给 `psql`，但不支持并行和选择性恢复。

备份不只包含表：角色、所有权和权限通常由集群级命令另行保存。生产备份使用 `ops/postgres/backup.sh journal`；当前线上 MakeItSpecific 仍使用兼容库名 `alfred`，因此执行 `ops/postgres/backup.sh alfred`。完成单独迁移后可改用 `makeitspecific`，通过 systemd timer 每日运行，脚本保留最近 7 天，并用 `pg_restore --list` 校验文件。

恢复前确认目标数据库、备份文件和业务窗口；`restore.sh` 要求输入 `RESTORE <database>`，避免误覆盖。建议先创建临时数据库做演练：`createdb journal_restore_test && pg_restore --dbname=journal_restore_test backup.dump`，检查 Alembic 版本、行数和应用健康检查，再删除临时库。

完整恢复顺序是：部署 PostgreSQL volume，创建角色/数据库，恢复角色权限，恢复项目 dump，运行 Alembic 校验，启动应用并执行登录/CRUD 冒烟测试。常见错误包括密码未设置、目标数据库不存在、角色不存在、扩展版本不匹配和 dump 与服务器版本差异。

RPO 是可接受的数据丢失窗口，RTO 是恢复服务所需时间。每日备份的 RPO 通常接近 24 小时；本机备份不能抵御磁盘损坏、勒索或整机故障，必须复制到异地/对象存储。没有实际验证过恢复的备份不能算可靠备份。
