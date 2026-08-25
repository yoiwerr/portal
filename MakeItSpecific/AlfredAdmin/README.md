# AlfredAdmin — Alfred 管理后台

> 用户认证、模型配置、用量统计。Alfred 的配套管理服务，不是 API 网关。

---

## 定位

AlfredAdmin 是 [Alfred](../)（AI 工作流增强 Agent）的**管理后台**，负责：

- **用户认证** — 注册、登录、JWT、refresh token 轮转
- **模型配置管理** — LLM provider 的增删改查，API Key 只存环境变量名
- **Token 用量追踪** — 每次 LLM 调用的输入/输出 token 统计
- **请求日志** — 管理接口的访问记录

AlfredAdmin **不代理** Alfred 的对话流量。对话请求由 nginx 直接反代到 Alfred Python 服务。

```
Browser
  │
  ▼
nginx
  ├── /alfred/*   ──→  Alfred (Python :8001)    ← 对话主链路
  └── /admin/*    ──→  AlfredAdmin (Go :8080)    ← 管理后台
```

### 与 Alfred 的关系

AlfredAdmin 和 Alfred **共享同一个 PostgreSQL 数据库**（`alfred`），通过 `admin_` 前缀表协作：

| 表 | 谁写 | 谁读 | 用途 |
|----|------|------|------|
| `admin_users` | AlfredAdmin | AlfredAdmin | 用户账号 |
| `admin_model_configs` | AlfredAdmin | Alfred（待接入） | LLM 模型配置 |
| `admin_token_usage` | Alfred（待接入） | AlfredAdmin | 用量统计 |
| `admin_refresh_tokens` | AlfredAdmin | AlfredAdmin | 登录态持久化 |
| `admin_request_logs` | AlfredAdmin | AlfredAdmin | 请求审计 |

---

## 快速开始

### 前置依赖

- Go 1.22+
- PostgreSQL（与 Alfred 共用 `alfred` 数据库）

### 本地开发

```bash
cd AlfredAdmin

# 安装依赖
go mod tidy

# 配置环境变量
export DATABASE_URL="postgres://postgres:postgres@localhost:5432/alfred?sslmode=disable"
export JWT_SECRET="dev-secret-key-at-least-32-characters-long!!"
export ADMIN_INIT_PASSWORD="admin123"
export DEEPSEEK_API_KEY="sk-your-key"

# 运行
go run ./cmd/gateway
```

启动后访问：
- **管理界面**: http://localhost:8080/admin/
- **登录页**: http://localhost:8080/auth/
- **健康检查**: http://localhost:8080/api/v1/health

### Docker Compose

```bash
docker compose up -d
```

首次启动自动创建 admin 用户（密码由 `ADMIN_INIT_PASSWORD` 指定，默认 `admin123`）和默认 DeepSeek 模型配置。

---

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `ADMIN_PORT` | `8080` | 监听端口 |
| `JWT_SECRET` | (必填) | JWT 签名密钥（至少 32 字符） |
| `JWT_ACCESS_EXPIRY` | `15m` | Access token 有效期 |
| `JWT_REFRESH_EXPIRY` | `168h` | Refresh token 有效期（7 天） |
| `ADMIN_INIT_PASSWORD` | `admin123` | 初始化 admin 密码（仅首次启动） |
| `DATABASE_URL` | (必填) | PostgreSQL 连接串 |
| `DEEPSEEK_API_KEY` | (可选) | DeepSeek API Key |
| `OPENAI_API_KEY` | (可选) | OpenAI API Key |
| `DASHSCOPE_API_KEY` | (可选) | DashScope API Key |

---

## API

### 健康检查

```
GET /api/v1/health
→ {"status": "ok", "service": "alfred-admin"}
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
GET /api/v1/admin/stats/tokens         Token 用量汇总 + 按模型拆分 + 最近调用
GET /api/v1/admin/stats/tokens/recent  最近 50 条调用记录
GET /api/v1/admin/stats/requests       请求日志统计
```

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
AlfredAdmin/
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
| 数据库 | PostgreSQL（pgx/v5，与 Alfred 共用 `alfred` 库） |
| 认证 | bcrypt + JWT (golang-jwt/v5)，refresh token 存 DB |
| 前端 | 原生 HTML/CSS/JS（登录页 + 管理面板） |
| 部署 | Docker 多阶段构建（golang:1.22-alpine → alpine:3.20） |

---

## License

MIT
