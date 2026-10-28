# dude-admin — dude 管理后台

> 用户认证、模型配置、用量统计。dude 的配套管理服务，不是 API 网关。

---

## 定位

dude-admin 是 [dude](../README.md)（面向新手的 Vibe Coding 方案助手）的**管理后台**，负责：

- **用户认证** — 注册、登录、JWT、refresh token 轮转
- **模型配置管理** — LLM provider 的增删改查，API Key 只存环境变量名
- **Token 用量追踪** — 每次 LLM 调用的输入/输出 token 统计
- **请求日志** — 管理接口的访问记录

dude-admin **不代理** dude 的对话流量。对话请求由 nginx 直接反代到 dude Python 服务。

产品范围以 [产品定义](../PRODUCT.md) 为准。账号、模型配置和统计属于 dude 自身的运行基础设施，不是向用户交付的项目实现能力。

## 管理员与普通用户

所有账号使用同一个登录入口。身份由后端签发并验证，不提供自行选择管理员的注册选项：注册始终创建 `user`；首次启动的管理员由 `ADMIN_INIT_PASSWORD` 初始化。

| 身份 | 页面与权限 |
| --- | --- |
| 普通用户 `user` | 使用对话页，顶部显示普通用户；访问管理数据接口返回 403 |
| 管理员 `admin` | 对话页有「管理后台」入口；查看用户资料和近 30 天用量，保留原有模型配置管理 |

管理后台的「用户与身份」列出用户名、完整用户 ID、角色、启用状态、注册时间、近 30 天模型调用次数、输入/输出/总 Token、该区间的最近调用时间。支持用户名包含搜索、完整 ID 查询、角色筛选和分页；零调用账号也会列出。此轮为只读用户目录，不提供调整角色或停用账号的操作。

「用量概览」统计当前用户数、管理员数、启用账号数和滚动 30 天内已记录的调用及 Token（UTC 计算区间，浏览器按本地时区显示）。数据来自 `admin_users`、`admin_token_usage`，没有新增表或迁移。不会返回密码哈希、refresh token 或对话内容。

用量仅供参考，不是账单：一次对话包含多次规划节点调用；异步写入可能略有延迟，失败写入/无 usage 的响应不计入，历史数据和未接入记录的上下文摘要等调用可能缺失。中转站返回的 usage 可能包含额外开销，应与服务商账单核对。未登录的旧本地预览不会记录实名用量。模型名称优先使用响应中的真实标识，旧记录里的 planner 等节点名称不会自动改写。总概览包含未归属或已删除用户的历史调用，因此不一定等于当前用户列表之和。

```
Browser
  │
  ▼
nginx
  ├── /dude/                     ──→ dude (容器内 Python :8000)
  └── /dude/auth/、/dude/admin/ ──→ dude-admin (Go :8080)
```

认证和管理 API 分别通过 `/dude/api/v1/auth/` 和 `/dude/api/v1/admin/` 路由到 dude-admin，旧路径 `/dude/api/auth/` 和 `/dude/api/admin/` 仍兼容。nginx 先重写路径，再使用不带 URI 的变量 `proxy_pass`，保留 `login`、`me`、静态文件名和查询参数；准确规则见 [nginx 配置](../../nginx/default.conf)。本地直接运行 Python 时默认端口为 8001。

### 与 dude 的关系

dude-admin 和 dude **共享同一个 PostgreSQL 数据库**（`alfred`），通过 `admin_` 前缀表协作：

| 表 | 谁写 | 谁读 | 用途 |
|----|------|------|------|
| `admin_users` | dude-admin | dude-admin | 用户账号 |
| `admin_model_configs` | dude-admin | dude（待接入） | LLM 模型配置 |
| `admin_token_usage` | dude 规划节点 | dude-admin | 已记录的用量统计 |
| `admin_refresh_tokens` | dude-admin | dude-admin | 登录态持久化 |
| `admin_request_logs` | dude-admin | dude-admin | 请求审计 |

---

## 快速开始

### 前置依赖

- Go 1.22+
- PostgreSQL（与 dude 共用 `alfred` 数据库）

### 本地开发

本节是**单独调试 Go 认证/管理服务**，不是整个 Portal 的启动入口。统一启动从 [Portal 根目录](../../README.md#本地开发) 执行 `make dev`，它将 Go 构建到临时目录并监听 127.0.0.1:8083，通过 Portal 提供登录与管理入口。独立调试仍建议 `ADMIN_PORT=8083`，不要与正在运行的统一启动器重复启动。

```bash
cd /home/yoiwerr/portal/dude/dude-admin

# 安装依赖
go mod download

# 先安全配置并导出这些变量；JWT_SECRET 必须与 Python 服务一致
: "${DATABASE_URL:?请配置可访问的 alfred 数据库连接串}"
: "${JWT_SECRET:?请配置至少 32 字符的签名密钥}"
: "${ADMIN_INIT_PASSWORD:?请配置初始化管理员密码}"

# Go 服务只读取进程环境；上述变量需 export，不会自动读取 Portal 的 .env
export DATABASE_URL JWT_SECRET ADMIN_INIT_PASSWORD
export ADMIN_PORT=8083

# 运行
go run ./cmd/gateway
```

启动后访问：
- **管理界面**: http://localhost:8083/admin/
- **登录页**: http://localhost:8083/auth/
- **健康检查**: http://localhost:8083/api/v1/health

该地址用于独立检查认证与管理服务，不会同时启动 Python 聊天服务。生产统一入口为 `/dude/auth/` 和 `/dude/admin/`。临时预览的测试账号仅存在于隔离测试库，未创建或修改生产管理员账号；真实管理员密码以部署时首次初始化的配置为准。

### Docker Compose

在 Portal 根目录操作，先完成已有 `.env`、数据库和共享密钥配置；子目录 Compose 依赖根级 PostgreSQL，不是独立部署包：

```bash
cd /home/yoiwerr/portal
docker compose up -d --build dude-admin
```

首次启动自动创建 admin 用户（密码由 `ADMIN_INIT_PASSWORD` 指定）和默认 DeepSeek 模型配置。更改初始化密码不等于修改已存在账号的密码。

根级 Compose 要求显式提供 `JWT_SECRET` 和 `ADMIN_INIT_PASSWORD`。直接 `go run` 的现有代码仍有弱默认值，必须显式配置，不能将直接运行方式视为与 Compose 相同的生产校验。

---

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `ADMIN_PORT` | `8080` | 监听端口 |
| `ADMIN_HOST` | 空（所有网卡） | 本机预览可设为 `127.0.0.1`；容器保持默认，由内部网络和端口映射控制访问 |
| `JWT_SECRET` | Compose 必填；直跑有旧默认 | 显式设置至少 32 字符，与 Python 共用 |
| `JWT_ACCESS_EXPIRY` | `15m` | Access token 有效期 |
| `JWT_REFRESH_EXPIRY` | `168h` | Refresh token 有效期（7 天） |
| `ADMIN_INIT_PASSWORD` | Compose 必填；直跑旧默认 `admin123` | 必须显式设置，初始化 admin 密码（仅首次启动） |
| `DATABASE_URL` | 直跑有旧默认；Compose 注入 | 显式设置正确的 PostgreSQL 连接串，不使用旧弱凭证 |
| `DEEPSEEK_API_KEY` | (可选) | DeepSeek API Key |
| `OPENAI_API_KEY` | (可选) | OpenAI API Key |
| `DASHSCOPE_API_KEY` | (可选) | DashScope API Key |

---

## API

### 健康检查

```
GET /api/v1/health
→ {"status": "ok", "service": "dude-admin"}
```

### Auth（公开）

```
POST /api/v1/auth/register    {"username": "...", "password": "..."}
POST /api/v1/auth/login       {"username": "...", "password": "..."}
POST /api/v1/auth/refresh     {"refresh_token": "..."}
POST /api/v1/auth/logout      {"refresh_token": "..."}    (需 JWT)
GET  /api/v1/auth/me                                      (需 JWT)
```

**Login 响应：**
```json
{
  "access_token": "eyJhbGci...",
  "refresh_token": "uuid-uuid",
  "token_type": "Bearer",
  "expires_in": 900
}
```

### Admin — 模型管理（需 JWT + admin 角色）

```
POST   /api/v1/admin/models              创建模型配置
GET    /api/v1/admin/models              列出所有模型
PUT    /api/v1/admin/models/{id}         更新模型配置
DELETE /api/v1/admin/models/{id}         删除模型配置
PUT    /api/v1/admin/models/{id}/toggle  启用/禁用    {"enabled": true}
PUT    /api/v1/admin/models/{id}/default 设为默认
```

**创建模型请求：**
```json
{
  "alias": "deepseek-chat",
  "provider": "deepseek",
  "model_name": "deepseek-chat",
  "base_url": "https://api.deepseek.com/v1",
  "api_key_env_var": "DEEPSEEK_API_KEY"
}
```

> `api_key_env_var` 只存环境变量**名称**，实际 API Key 在调用时从 `os.Getenv()` 读取，永远不落数据库。

### Admin — 统计（需 JWT + admin 角色）

```
GET /api/v1/admin/overview            当前账号数量 + 近 30 天用量
GET /api/v1/admin/users               用户资料 + 各用户近 30 天用量
GET /api/v1/admin/stats/tokens         Token 用量汇总 + 按模型拆分 + 最近调用
GET /api/v1/admin/stats/tokens/recent  最近 50 条调用记录
GET /api/v1/admin/stats/requests       请求日志统计
```

`/admin/users` 查询参数：`q`（最多 64 字符，按用户名包含或完整用户 ID 搜索）、`role`（空、`admin`、`user`）、`page`（默认 1）、`page_size`（默认 20，最大 100）。返回 `users`、`total`、`page`、`page_size`、`period_start`、`as_of`。旧 `/stats/*` 接口保留原有全时间范围含义。

### 验证与部署

```bash
go test ./...
go vet ./...
# 可选真实数据库集成测试；只能指向名称以 alfred_roles_test 开头的临时数据库
ALFRED_ADMIN_TEST_DATABASE_URL='postgres://.../alfred_roles_test' go test ./internal/handler -run TestUserDirectoryPostgres -v
```

集成测试在独立 schema 中验证真实注册/登录、401/403、注册不能提权、用户筛选和分页、零调用账号、30 天边界以及统计汇总；结束后删除该测试 schema。未配置测试库时该测试明确跳过。

部署更新代码后，在 Portal 根目录运行 `docker compose up -d --build dude-admin dude-api`，再以管理员登录 `/dude/` 并打开管理后台。此次不需新环境变量或数据库迁移，保留原有 `.env`、账号和数据库。`ADMIN_INIT_PASSWORD` 不会重置已存在账号的密码；不要为启用页面重建数据库或覆盖已有凭据。

### 错误格式

所有错误返回统一结构：

```json
{
  "error": {
    "code": "UNAUTHORIZED",
    "message": "Invalid or expired token",
    "request_id": "550e8400-e29b-41d4-a716-446655440000"
  }
}
```

错误码：`VALIDATION_ERROR`、`UNAUTHORIZED`、`FORBIDDEN`、`NOT_FOUND`、`CONFLICT`、`RATE_LIMITED`、`INTERNAL_ERROR`。

每个响应头带 `X-Request-ID`。

---

## 项目结构

```
dude-admin/
├── cmd/gateway/main.go           ← 入口，组装所有依赖
├── config/config.go              ← 环境变量加载
├── internal/
│   ├── handler/
│   │   ├── auth.go               ← 注册、登录、登出、刷新、me
│   │   ├── model.go              ← 模型配置 CRUD
│   │   ├── stats.go              ← Token 用量 + 请求统计
│   │   ├── middleware.go         ← RequestID、日志、JWT 鉴权、admin 守卫
│   │   └── context.go            ← Context 中存取 user claims
│   ├── service/
│   │   ├── auth.go               ← 认证业务逻辑（bcrypt、JWT、refresh token）
│   │   ├── model.go              ← 模型配置 CRUD
│   │   └── stats.go              ← 统计查询
│   ├── model/models.go           ← 领域结构体（User、ModelConfig、TokenUsage、RequestLog）
│   └── store/
│       └── postgres.go           ← PostgreSQL 连接池 + 迁移执行
├── migrations/
│   ├── 001_init.up.sql           ← 完整建表（admin_users / model_configs / token_usage / refresh_tokens / request_logs）
│   └── 001_init.down.sql         ← 删表回滚
├── pkg/response/response.go      ← 统一 JSON 响应 + 错误格式
├── static/                       ← 管理前端页面（login.html + admin.html）
├── Dockerfile
├── docker-compose.yml
└── README.md
```

---

## 技术栈

| 层 | 技术 |
|----|------|
| 语言 | Go 1.22 |
| 路由 | chi/v5 |
| 数据库 | PostgreSQL（pgx/v5，与 dude 共用 `alfred` 库） |
| 认证 | bcrypt + JWT (golang-jwt/v5)，refresh token 存 DB |
| 前端 | 原生 HTML/CSS/JS（登录页 + 管理面板） |
| 部署 | Docker 多阶段构建（golang:1.22-alpine → scratch） |

---

## License

MIT
