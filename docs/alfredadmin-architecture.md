# Alfred 架构设计 v3

> 2026-08-09 最终版：Go 管理面 + Python AI 引擎，各司其职，同级协作，不互相代理。

---

## 一、v1 → v2 → v3 的演进

| | v1 (错) | v2 (对了一半) | v3 (最终) |
|---|---|---|---|
| **Go 的角色** | 代理层，挡在 Python 前面 | 不存在 | **管理面**：Auth + Admin + 统计 |
| **Python 的角色** | AI 引擎 | 全干 | **数据面**：Chat + Agent + RAG |
| **Go↔Python 关系** | Go 代理 Python | — | **同级服务**，nginx 路由分发 |
| **SSE 路径** | Browser→Go→Python | Browser→Python | Browser→Python（不变，Go 不碰） |
| **Go 存在的价值** | 零（纯转发） | — | **编译时安全 + 高性能管理 API + 练 Go** |

---

## 二、架构全景

```
                              ┌──────────────────────────────┐
                              │         Portal Nginx          │
                              │   /          → 首页           │
                              │   /api       → ChatLab        │
                              │   /chatlab   → Streamlit      │
                              │                              │
                              │   /alfred/           → Python │  ← AI 引擎
                              │   /alfred/api/auth/  → Go     │  ← 认证
                              │   /alfred/api/admin/ → Go     │  ← 管理后台
                              │   /alfred/auth/      → Go     │  ← 登录页
                              │   /alfred/admin/     → Go     │  ← 管理页
                              └──────┬───────────┬───────────┘
                                     │           │
                    ┌────────────────▼──┐   ┌───▼──────────────────┐
                    │  Admin (Go)       │   │  Alfred (Python)      │
                    │  chi, :8080       │   │  FastAPI, :8000       │
                    │                   │   │                       │
                    │  管理面           │   │  数据面               │
                    │  ───────────────  │   │  ────────────────     │
                    │  /api/auth/*      │   │  /api/chat/stream     │
                    │  /api/admin/*     │   │  /api/sessions/*      │
                    │  /auth/ (登录页)  │   │  /api/knowledge/*     │
                    │  /admin/ (管理页) │   │  /api/feedback/*      │
                    │                   │   │  /api/files/*         │
                    │                   │   │  /api/handover/*      │
                    │                   │   │  / (对话页)           │
                    └────────┬──────────┘   └───┬──────────────────┘
                             │                  │
                             │    ┌─────────────┘
                             │    │
                    ┌────────▼────▼───────────┐
                    │     PostgreSQL           │
                    │     alfred DB            │
                    │                         │
                    │  Go 管理:               │
                    │    users                │
                    │    model_configs        │
                    │    token_usage          │
                    │    refresh_tokens       │
                    │    request_logs         │
                    │                         │
                    │  Python 使用:           │
                    │    sessions             │
                    │    messages             │
                    │    feedback             │
                    │    session_memory       │
                    │    user_profiles        │
                    │    task_contracts       │
                    │    + PGVector (向量)    │
                    └────────────────────────┘
```

**关键：Go 和 Python 不互相调用。它们共享一个 DB，各自读写自己负责的表。JWT 密钥共享，各自独立验证。**

---

## 三、请求流

### 登录流程

```
Browser                                  Go (:8080)              Python (:8000)
  │                                          │                        │
  │  打开 /alfred/ (Python 对话页)           │                        │
  ├──────────────────────────────────────────┼────────────────────────▶
  │                                          │                        │  chat.js 检查
  │                                          │                        │  localStorage
  │                                          │                        │  无 JWT → JS 跳转
  │                                          │                        │
  │  GET /alfred/auth/                       │                        │
  ├─────────────────────────────────────────▶│                        │
  │  ◀── login.html ────────────────────────│                        │
  │                                          │                        │
  │  POST /alfred/api/auth/login             │                        │
  │  {"username":"admin","password":"xxx"}    │                        │
  ├─────────────────────────────────────────▶│                        │
  │                                          │  users 表验证          │
  │                                          │  bcrypt 比对           │
  │                                          │  签发 JWT              │
  │  ◀── {"access_token":"...","user":{...}} │                        │
  │                                          │                        │
  │  auth.js: localStorage.set("token", t)   │                        │
  │  auth.js: window.location = "/alfred/"   │                        │
  │                                          │                        │
  │  GET /alfred/  (带 token)                │                        │
  ├──────────────────────────────────────────┼────────────────────────▶
  │                                          │                        │  chat.js 读到 token
  │                                          │                        │  正常加载对话页
```

### 对话流程（Go 完全不参与）

```
Browser                                  Go (:8080)              Python (:8000)
  │                                          │                        │
  │  POST /alfred/api/chat/stream            │                        │
  │  Authorization: Bearer <jwt>             │                        │
  ├──────────────────────────────────────────┼────────────────────────▶
  │                                          │                        │  Depends() 验证 JWT
  │                                          │                        │  （用共享 secret 自验）
  │                                          │                        │  LangGraph Agent Loop
  │  ◀── SSE: token, tool_call, done ────────┼────────────────────────│
  │                                          │                        │
  │                                          │  ← Go 完全不知情       │
```

### 管理流程（Python 完全不参与）

```
Browser                                  Go (:8080)              Python (:8000)
  │                                          │                        │
  │  点"管理" → GET /alfred/admin/           │                        │
  ├─────────────────────────────────────────▶│                        │
  │  ◀── admin.html ────────────────────────│                        │
  │                                          │                        │
  │  GET /alfred/api/admin/stats/tokens      │                        │
  │  Authorization: Bearer <jwt>             │                        │
  ├─────────────────────────────────────────▶│                        │
  │                                          │  验证 JWT + admin 角色 │
  │                                          │  查 token_usage 表     │
  │  ◀── {"summary":{...},"recent":[...]} ──│                        │
```

---

## 四、Go Admin 职责

| 模块 | 细节 |
|------|------|
| **用户认证** | 注册/登录/JWT 签发/Refresh Token 轮转/bcrypt |
| **管理后台页面** | Go 内嵌静态文件或 `embed`，直接 serve admin UI |
| **登录页面** | 同上，Go 提供 login.html |
| **模型配置 CRUD** | 增删改查、启用/禁用、设默认、API Key env var 管理 |
| **Token 用量统计** | 聚合查询（按模型/按时间/按用户）+ 最近调用列表 |
| **请求日志** | 记录所有请求的 method/path/status/duration/IP |
| **用户管理** | admin 可创建/禁用用户 |
| **API Key 管理** | 三级回退：模型 env var → provider 默认 → 空 |

## Python Alfred 职责

| 模块 | 细节 |
|------|------|
| **对话 SSE** | 核心聊天端点，验证 JWT（共享 secret） |
| **LangGraph Agent Loop** | 意图路由→RAG→Planner→Clarify→Execute→Checkpoint→Reflect |
| **Token 用量写入** | 每次 LLM 调用后异步写 `token_usage` 表（Go 来读） |
| **会话/知识库/反馈** | 已有模块，加 `user_id` 过滤 |
| **对话页** | index.html + chat.js，顶部显示登录状态 |

---

## 五、共享协议

### JWT 密钥共享

```
.env (Portal 层)
  JWT_SECRET=同一串32位密钥
  → Go config:     os.Getenv("JWT_SECRET")
  → Python config: os.getenv("JWT_SECRET")
```

Go 签发 JWT，Python 自验。无需内部 API 调用。

### 数据库共享

```
同一个 PostgreSQL 实例，同一个 alfred 数据库：

Go 建的表（migrations）：          Python 建的表（session_store.py）：
  users                              sessions
  model_configs                      messages
  token_usage                        feedback
  refresh_tokens                     session_memory (PGVector)
  request_logs                       user_profiles  (PGVector)
                                     task_contracts
```

Go 用 `golang-migrate` 管理自己的 5 张表。Python 用 `_init_db()` 管理自己的表。互不冲突，各自 DDL。

### 跨服务数据流

```
Python: LLM 调用完成
  → psycopg INSERT INTO token_usage (user_id, provider, model_name, tokens, ...)
  → 写完不管了
                              Go: admin 用户打开用量看板
                                → SELECT SUM(total_tokens) FROM token_usage ...
                                → 渲染图表

Go: admin 在管理页面新增模型 "gpt-4o-mini"
  → INSERT INTO model_configs (alias, provider, model_name, api_key_env_var, ...)

                              Python: 用户说"用 gpt-4o-mini 帮我..."
                                → query model_configs WHERE alias='gpt-4o-mini'
                                → resolve_api_key() → os.getenv(env_var)
                                → 调用 OpenAI API
```

---

## 六、Token 用量管理

### Python 侧：产生数据

```python
# core/llm_client.py

async def _record_usage_async(conn_string, user_id, provider, model_name,
                               input_tokens, output_tokens, duration_ms, success):
    """在独立线程中写入，不阻塞 agent loop"""
    import psycopg
    conn = psycopg.connect(conn_string)
    conn.execute("""
        INSERT INTO token_usage (user_id, provider, model_name,
            input_tokens, output_tokens, total_tokens, duration_ms, success)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """, (user_id, provider, model_name, input_tokens, output_tokens,
          input_tokens + output_tokens, duration_ms, success))
    conn.commit()
    conn.close()

# graph.py execute_node 中调用:
asyncio.create_task(
    asyncio.to_thread(_record_usage_async, ...)
)
```

### Go 侧：消费数据

```sql
-- 汇总
SELECT provider, model_name,
       COUNT(*) as calls,
       SUM(total_tokens) as total_tokens,
       AVG(duration_ms) as avg_ms,
       COUNT(*) FILTER (WHERE success) * 100.0 / COUNT(*) as success_rate
FROM token_usage
WHERE created_at > NOW() - INTERVAL '30 days'
GROUP BY provider, model_name
ORDER BY total_tokens DESC;

-- 最近 50 条
SELECT tw.*, u.username
FROM token_usage tw LEFT JOIN users u ON tw.user_id = u.id
ORDER BY tw.created_at DESC LIMIT 50;
```

---

## 七、API Key 管理

### 存储模型

```
model_configs 表（Go 管理，Go 和 Python 都能读）

┌────┬──────────────┬──────────┬──────────────┬──────────────────────┬─────────┐
│ id │ alias        │ provider │ model_name   │ api_key_env_var      │ default │
├────┼──────────────┼──────────┼──────────────┼──────────────────────┼─────────┤
│ 1  │ deepseek-chat│ deepseek │ deepseek-chat│ DEEPSEEK_API_KEY     │ true    │
│ 2  │ gpt-4o       │ openai   │ gpt-4o       │ OPENAI_API_KEY       │ false   │
│ 3  │ qwen-plus    │ dashscope│ qwen-plus    │ DASHSCOPE_API_KEY    │ false   │
│ 4  │ my-custom    │ deepseek │ deepseek-r1  │ MY_DEEPSEEK_KEY      │ false   │
└────┴──────────────┴──────────┴──────────────┴──────────────────────┴─────────┘
```

### 三级回退解析（Python `resolve_api_key`）

```python
def resolve_api_key(model_config: dict) -> str:
    """
    Level 1: 该模型指定的 env var 有值 → 用
    Level 2: 按 provider 回退到 .env 里的默认 key（你的 key）
    Level 3: 空字符串
    """
    # L1
    key = os.getenv(model_config["api_key_env_var"], "")
    if key:
        return key

    # L2 — 你的默认 key，配在 .env 里
    provider_keys = {
        "deepseek":  config.deepseek_api_key,
        "openai":    config.openai_api_key,
        "dashscope": config.dashscope_api_key,
    }
    return provider_keys.get(model_config["provider"], "")
```

### 管理页面操作

```
/admin → "模型" Tab

┌──────────────────────────────────────────────────────────┐
│  🤖 模型管理                               [+ 添加模型]  │
│                                                          │
│  ┌──────────────────────────────────────────────────┐    │
│  │ deepseek-chat  ✅ 启用  ● 默认                    │    │
│  │ provider: deepseek                               │    │
│  │ key 来源: DEEPSEEK_API_KEY                       │    │
│  │           → 从 .env 读取 (sk-xxxx...abcd)         │    │
│  │ 说明: 用系统默认 key                              │    │
│  │                              [编辑] [禁用]        │    │
│  └──────────────────────────────────────────────────┘    │
│                                                          │
│  ┌──────────────────────────────────────────────────┐    │
│  │ gpt-4o       ✅ 启用                              │    │
│  │ provider: openai                                 │    │
│  │ key 来源: OPENAI_API_KEY                         │    │
│  │           → 未设置，回退到 .env OPENAI_API_KEY     │    │
│  │           → .env 也未设置 ≡ 不可用 ⚠              │    │
│  │                              [编辑] [禁用]        │    │
│  └──────────────────────────────────────────────────┘    │
│                                                          │
│  规则: 每模型可指定环境变量名 → 未设置就用 .env 默认 key │
└──────────────────────────────────────────────────────────┘
```

### 更换 key 的操作

```
admin 想临时换一个 DeepSeek key:

1. ssh 到服务器: export TEMP_DEEPSEEK_KEY="sk-new-key"
   (或者写到 .env 里)
2. 打开 /alfred/admin/ → 模型 → deepseek-chat → 编辑
3. api_key_env_var: DEEPSEEK_API_KEY → TEMP_DEEPSEEK_KEY
4. 保存 → 下次 LLM 调用就读新 key

用完切回来:
5. api_key_env_var: TEMP_DEEPSEEK_KEY → DEEPSEEK_API_KEY
6. 保存 → 回到默认 key
```

---

## 八、路由分配

```nginx
# ═══ Go Admin (管理面) ═══
location /alfred/api/auth/ {
    proxy_pass http://admin:8080/api/v1/auth/;   # Go
}
location /alfred/api/admin/ {
    proxy_pass http://admin:8080/api/v1/admin/;   # Go
}
location /alfred/auth/ {
    proxy_pass http://admin:8080/static/;          # Go 登录页
}
location /alfred/admin/ {
    proxy_pass http://admin:8080/static/admin/;    # Go 管理页
}

# ═══ Python Alfred (数据面) ═══
location /alfred/ {
    proxy_pass http://alfred-api:8000/;            # Python 对话页 + 所有 API
}
```

nginx 按前缀拆分：`/alfred/api/auth/` 和 `/alfred/api/admin/` 走 Go；其余走 Python。`/alfred/` 的 location 优先级最低，作为 fallback。

---

## 九、Go 项目结构（精简后）

之前 AlfredAdmin（原 AgentGateway）的问题是定位不清。新定位明确后，精简为：

```
MakeItSpecific/
│
├── AlfredAdmin/                    # Go Admin (管理面)
│   ├── cmd/admin/main.go           # 入口
│   ├── config/config.go            # 环境变量
│   │
│   ├── internal/
│   │   ├── handler/
│   │   │   ├── auth.go             # register/login/refresh/logout/me
│   │   │   ├── model.go            # 模型 CRUD + toggle + default
│   │   │   ├── stats.go            # Token 用量 + 请求日志统计
│   │   │   └── middleware.go       # JWT 验证 / AdminOnly / RequestID / Logging
│   │   │
│   │   ├── service/
│   │   │   ├── auth.go             # bcrypt + JWT + refresh token + seed
│   │   │   ├── model.go            # 模型配置 CRUD
│   │   │   └── stats.go            # 用量聚合查询
│   │   │
│   │   ├── model/models.go         # User, ModelConfig, TokenUsage, RequestLog
│   │   └── store/postgres.go       # 连接池 + 迁移
│   │
│   ├── migrations/
│   │   ├── 001_init.up.sql
│   │   └── 001_init.down.sql
│   │
│   ├── static/                     # 内嵌前端
│   │   ├── login.html / admin.html
│   │   ├── css/  (login.css + admin.css)
│   │   └── js/   (auth.js + admin.js)
│   │
│   ├── Dockerfile
│   ├── docker-compose.yml
│   └── go.mod / go.sum
│
├── app.py                          # Alfred FastAPI 入口
├── core/  graph.py / agent.py / ...  # LangGraph Agent Loop
├── routers/  chat.py / sessions.py / ...  # API 路由 (含 deps.py)
├── services/  rag / vector / usage / ...  # 业务服务
├── static/  index.html / ...       # 对话页前端
├── docker-compose.yml              # alfred-api + postgres
└── Dockerfile
```

**跟 v1 的区别：删掉了 `proxy.go`、`llm.go`、`redis_store.go`、`context.go`。不再代理任何 Python 流量，不再依赖 Redis。**

---

## 十、两个 Docker 服务

```
docker-compose.yml (portal 层)

services:
  nginx:       → 路由分发
  postgres:    → 共享数据库（ChatLab + Alfred + Admin）
  alfred-api:  → Python AI 引擎 (:8000)
  admin:       → Go 管理后台 (:8080)
  chatlab-api: → ChatLab FastAPI
  streamlit:   → ChatLab 前端
```

```
依赖链:

postgres ←── alfred-api  ←──┐
    ↑                        ├── nginx ←── Browser
    ├── admin ───────────────┘
    │
    ├── chatlab-api
    └── streamlit
```

Go 和 Python 平级，都只依赖 PostgreSQL。没有任何一个服务经过另一个服务。

---

## 十一、Python 侧更新（精简）

相比 v2，Python 不再需要：
- ~~`routers/auth.py`~~ → Go 负责
- ~~`routers/admin.py`~~ → Go 负责
- ~~`routers/deps.py` 中的 admin 相关~~ → 只需要 `get_current_user`
- ~~`services/auth_service.py`~~ → Go 负责
- ~~`services/model_service.py`~~ → Go 负责，Python 只读 model_configs
- ~~`static/login.html` 等~~ → Go 提供

Python 只加：
- `routers/deps.py` — `get_current_user` 依赖注入（JWT 自验）
- `services/usage_service.py` — 异步写 `token_usage` 表
- `core/llm_client.py` — 调用后埋点
- `routers/chat.py` / `sessions.py` — 加 `Depends(get_current_user)`

---

## 十二、实现计划

### 阶段 1：Go Admin 后端（复用已有的 80% 代码）

| # | 任务 | 说明 |
|---|------|------|
| 1 | 删减 AlfredAdmin | 去掉 `proxy.go` `llm.go` `redis_store.go` `context.go`，去掉 Redis 依赖 |
| 2 | 迁移改为 shared DB | Admin 连 alfred DB，不再独立 DB |
| 3 | 内嵌前端静态文件 | `//go:embed static/*`，Go 直接 serve login + admin 页面 |
| 4 | 跑通 `go mod tidy` + 编译 | 生成 go.sum |

### 阶段 2：Python 侧加 JWT 验证 + 用量埋点

| # | 任务 | 说明 |
|---|------|------|
| 5 | `deps.py` | `get_current_user` → 从 Authorization header 解 JWT（共享 secret） |
| 6 | `usage_service.py` | `record_usage()` 异步写入 |
| 7 | `chat.py` + `sessions.py` | 加 `Depends(get_current_user)` |
| 8 | `llm_client.py` / `graph.py` | LLM 调用后埋点写 token_usage |

### 阶段 3：前端

| # | 任务 | 说明 |
|---|------|------|
| 9 | Go `static/login.html` + `auth.js` | 登录注册表单，调 Go auth API |
| 10 | Go `static/admin.html` + `admin.js` | 仪表盘 + 模型管理 + 用量看板 |
| 11 | Python `static/index.html` + `chat.js` | 顶部加用户信息 + 管理入口，未登录跳 /alfred/auth/ |

### 阶段 4：集成

| # | 任务 | 说明 |
|---|------|------|
| 12 | nginx 路由 | `/alfred/api/auth/` `/alfred/api/admin/` `/alfred/auth/` `/alfred/admin/` → Go |
| 13 | docker-compose | 加 admin 服务
| 14 | 联调 | 登录→对话→管理后台全链路 |

---

## 十三、设计决策

1. **Go 不代理 Python** — v1 最大的错误。Go 和 Python 是同级服务，nginx 是唯一的代理层
2. **共享 DB，各自建表** — 不搞微服务那种"一个服务一个 DB"的教条。个人项目，共享 PostgreSQL，用表前缀或注释区分归属即可
3. **JWT 自验，不互调** — Go 签发 JWT，Python 用同一 secret 自验。零内部 API 调用，零耦合
4. **Go 做管理，Python 做 AI** — 各用各擅长的：Go 的类型安全做 CRUD 很舒服，Python 的生态做 AI/LangGraph 不可替代
5. **用 Go 内嵌前端** — `//go:embed static/*` 把 login.html 和 admin.html 编译进二进制，单文件部署
6. **三级 Key 回退** — 模型 env var → provider 默认 → 空。默认没配就用你的 key
7. **用量异步写入** — Python 用 `asyncio.to_thread` + psycopg 直写 DB，不阻塞 SSE。Go 只管读
