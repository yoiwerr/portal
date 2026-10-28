# dude-orchestrator：第一阶段

这是与现有 Python 服务并行的 TypeScript 服务。实现 Project Brief 和文档版本持久层、复用 Go 登录身份的实验 API；**未接入 Pi、聊天、Wiki 读取器和网页流量**。根级 `make dev` / Compose 仍启动原有服务。

产品边界以 [架构基线](../docs/dude-architecture-baseline.md) 为准：面向新项目，生成给编程 Agent 的技术方案与体验 Demo 的操作手册，不生成或执行项目代码。

## 技术和目录

- Node 22.23.4（`.node-version` / Dockerfile）、TypeScript、Fastify；依赖精确版本及 `package-lock.json`。
- `pg` 管连接，Kysely 管参数化 SQL，Zod 校验 JSON，jose 校验 Go HS256 JWT。
- `src/brief.ts`：Brief v1 与字段来源，最低生成条件是核心动作和可见结果。
- `src/repository.ts`：归属过滤、草稿冲突检查、不可变版本、任务和原子文档对。
- `src/auth.ts` / `src/app.ts`：认证与实验 HTTP 路由。
- `src/db/` / `migrations/`：连接、独立迁移历史及 SQL。
- `test/` / `scripts/test-postgres.sh`：单元、HTTP、真实 PostgreSQL 隔离测试。

## 本地试运行

先安装 Node 22.23.4 与 npm，在本目录执行：

```bash
npm ci --ignore-scripts
npm run build
cp .env.example .env
```

手动填写 `.env`，不要上传 Git：

| 变量 | 说明 |
| --- | --- |
| `DUDE_ORCHESTRATOR_DATABASE_URL` | 显式 PostgreSQL URL；密码中的特殊字符必须 URL 编码。指向 **Go 认证所在数据库**，现有安装通常为 `alfred`；不改名、不复制账号表 |
| `JWT_SECRET` | 与 Go dude-admin 相同，至少 32 字节；不生成第二套不兼容秘密，不使用默认值 |
| `DUDE_ORCHESTRATOR_HOST` | 默认 `127.0.0.1`；容器中为 `0.0.0.0` |
| `DUDE_ORCHESTRATOR_PORT` | 默认 `8010`；避免和现有 `make dev` 端口冲突 |

确认目标数据库正确、已有备份、Go 认证迁移已经完成（必须存在 `public.admin_users`）后：

```bash
node --env-file=.env dist/src/db/migrate.js
node --env-file=.env dist/src/server.js
```

没有 `.env` 自动加载，也没有启动时自动迁移。可以通过进程环境注入配置后使用 `npm run migrate` / `npm start`。缺少密码连接配置、JWT secret 或迁移未完成时启动失败，不回退到旧连接配置。迁移不会读 JWT_SECRET，运行 API 才需要它。

基础地址 `http://127.0.0.1:8010`。`/health/live` 检查进程，`/health/ready` 检查数据库、Go 用户表及迁移校验和。就绪失败返回 503；启动时就绪失败直接退出。健康检查不泄露连接串。

API 需要现有 Go 登录发出的 `Authorization: Bearer <access token>`，不是 Journal Cookie，也不是 refresh token。保留 JWT issuer `alfred-admin`。校验签名、有效期、subject/user_id 一致性，并实时检查账号 active；管理员没有读取他人项目的豁免。首次启动不会把旧 Python 会话转换成新项目。

| 方法 / 路径 | 行为 |
| --- | --- |
| `POST /api/v2/projects` | JSON `{ "title": "读书清单" }`，owner 从登录身份取，拒绝客户端指定 |
| `GET /api/v2/projects?limit=30&offset=0` | 当前用户的项目，最新优先，limit 最大 100 |
| `GET /api/v2/projects/:id` | 当前草稿及 revision |
| `DELETE /api/v2/projects/:id` | 永久删除本人的项目及新表中全部关联内容 |
| `GET /api/v2/projects/:id/versions` | 生成历史，包含失败记录，支持同样分页 |
| `GET /api/v2/projects/:id/versions/:version` | 冻结 Brief 及已完成文档对；未完成时两份文档均为 null |

他人项目与不存在项目均返回 404。没有 CORS 放行，没有公开生成、草稿写入或提交文档接口；下一阶段由协调器调用 Repository，用户仍通过对话修改资料。当前 HTTP 读写流程可测试，不能在该 API 中实际对话或生成方案。

## 数据和迁移约束

同一个产品继续复用现有 `alfred` 库，新增六张 `public.dude_*` 表（含迁移历史），不修改 Python/Go 既有表和迁移历史：

- `dude_projects` 关联 `admin_users`；`dude_brief_drafts` 保存 JSONB 和 revision。
- `dude_brief_versions` 冻结 Brief、草稿 revision、schema_version 和 Wiki 来源。Wiki 引用显式为 published / seed / none；第一阶段只存引用，不加载 Wiki。
- `dude_generation_runs` 保存状态、幂等键和错误类别，不保存模型请求正文。
- `dude_artifact_versions` 一行包含两份文档。复合外键约束两份文档、任务和 Brief 属于同一项目/版本。
- `dude_orchestrator_migrations` 保存文件名和 SHA-256；迁移使用事务与 advisory lock，重复执行无副作用，历史不匹配会中止。

草稿写入需 expected revision，过期写入返回冲突；生成时锁项目行，防止同时分配重复版本。幂等键绑定 revision/Wiki 来源，相同任务重试返回原任务，不能偷偷改变输入。每项目最多一个 running 任务；生成失败用新键发起下一版本，不覆盖旧版本。

已冻结 Brief 和文档由数据库触发器禁止 UPDATE。延迟约束确保成功状态和完整文档对一起提交，失败不发布半份内容，之前成功的文档保留。删除项目会级联清理。无破坏性 down migration；回退本阶段应用时停止新进程、保留新表即可，旧服务不受影响。不要编辑已执行 SQL，新增编号迁移。

归属隔离在 Repository/API 层实现，当前不使用 PostgreSQL RLS；拥有业务数据库凭证的进程仍属于信任边界。JWT 撤销跟随 Go access token 有效期及账号 active 状态。本阶段没有异步 Worker；将来接入 Pi 时必须实现任务租约、进程中断后的恢复/失败标记，再开放生成 API。

## 测试

```bash
npm ci --ignore-scripts
npm run typecheck
npm test
# Linux / WSL，非 root，已安装 PostgreSQL 开发工具（pg_config / initdb / pg_ctl）：
npm run test:db
```

`npm test` 未设置 `DUDE_TEST_DATABASE_URL` 时会明确跳过数据库集成项。`test:db` 在 `/tmp` 新建临时集群，默认端口 15438，随机密码和库名，完成后停止并删除本次集群。端口冲突会失败，不停止其他进程。可设置 `DUDE_TEST_PG_BIN` 与 `DUDE_TEST_PG_PORT` 指定工具位置/测试端口。

也可显式提供本机**空的一次性数据库** `DUDE_TEST_DATABASE_URL`。库名必须是 `dude_orchestrator_test_*` 且 public 无表，测试不会使用任何业务 URL 回退，也不会自动删除外部提供的数据库。测试会建立 Go 身份 fixture、旧表保护标记和新表，运行后该数据库不再为空，不能直接重用。

覆盖 JWT、未认证、停用账号、跨用户/管理员隔离、并发草稿冲突、生成幂等、版本不可变、失败回滚、完整文档对约束、删除级联与迁移幂等。不是实际 LLM 质量验证。

## 容器与后续接入

Dockerfile 使用 Node 22.23.4、多阶段构建、非 root 用户及 readiness 健康检查。构建命令 `docker build -t dude-orchestrator:0.1.0 .`。不自动加入根 Compose、不发布公网端口；后续接入时先显式运行迁移，再接共享数据库网络和 nginx 的实验路径，验证后才切换聊天流量。

第一阶段还没有 Pi、模型密钥配置、聊天消息表、LLM Wiki 在线适配、用量写入、React 页面和真实模型调用；这些不会因为“数据模型完成”被视为已经交付。
