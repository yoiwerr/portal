# Portal — 当前项目认知入口

更新：2026-10-20。适用于当前工作区（包括未提交改动），不是服务器状态报告。

先读 [AGENTS.md](AGENTS.md)，再按任务读取：

| 需要了解什么 | 文档 |
| --- | --- |
| 当前架构、路由、存储、启动限制、验证方式 | [项目认知](docs/project-context.md) |
| 全部版本文件在哪里、属于哪个模块 | [全文件索引](docs/project-file-index.md) |
| dude 产品边界 | [PRODUCT](dude/PRODUCT.md) |
| dude 节点、模块和代码定位 | [dude 模型地图](dude/CLAUDE.md) |
| 逐块优化范围 | [00–08 板块](dude/docs/product-modules.md) |
| 人工操作与启动 | [README](README.md) |
| ChatLab 停用、快照与回退 | [下线说明](docs/chatlab-retirement.md) |
| 数据库备份与恢复 | [运维资料](docs/postgresql-backup-and-restore.md) |

当前活跃服务为 `postgres`、`dude-api`、`dude-admin`、`journal`、`nginx`。dude 目录仍名为 dude；ChatLab 源码保留但退出网站。不要沿用旧“三服务”、SQLite/ChromaDB、ReAct 执行器等描述。

原文档中的 Session 记录已移至 [历史记录](docs/history/model-context-history.md)，不再混入当前架构。
