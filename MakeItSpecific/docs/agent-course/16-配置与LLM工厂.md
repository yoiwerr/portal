# 课程 16：配置系统与 LLM 工厂

> **难度**: 入门 | **预计阅读**: 15 分钟 | **前置**: 无

---

## 一、配置系统概览

```
.env 文件 (环境变量)
    │
    ▼
Config.from_env()  ← dataclass 自动加载
    │
    ├── LLM 配置 (provider, model, temperature, timeout)
    ├── 数据库配置 (pg_*)
    ├── RAG 配置 (top_k, chunk, rerank)
    ├── 追问配置 (clarify_threshold, max_rounds)
    ├── 沙箱配置 (sandbox_enabled, timeout)
    └── 路径配置 (project_root, data_dir, kb_dir, export_dir)
```

---

## 二、Config Dataclass

```python
@dataclass
class Config:
    # ── 路径 ──
    project_root: Path       # 项目根目录
    data_dir: Path           # 运行时数据
    knowledge_base_dir: Path # 知识库目录
    export_dir: Path         # 导出目录

    # ── API ──
    api_host: str = "0.0.0.0"
    api_port: int = 8001

    # ── PostgreSQL ──
    pg_host: str = "localhost"
    pg_port: int = 5432
    pg_database: str = "alfred"
    pg_user: str = "postgres"
    pg_password: str = ""

    # ── LLM ──
    llm_provider: str = "auto"     # dashscope|deepseek|openai|local|auto
    llm_model: str = "qwen-plus"
    llm_temperature: float = 0.7
    llm_timeout: float = 120.0

    # ── Provider-specific ──
    dashscope_api_key: str = ""
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com/v1"
    deepseek_model: str = "deepseek-chat"
    openai_api_key: str = ""
    openai_base_url: str = ""
    openai_model: str = "gpt-4o"
    local_llm_url: str = ""

    # ── RAG ──
    rag_top_k: int = 3
    rag_chunk_min: int = 200
    rag_chunk_max: int = 800
    similarity_threshold: float = 0.6
    rerank_enabled: bool = True
    rerank_model: str = "qwen3-rerank"
    rerank_top_k: int = 5
    rerank_coarse_k: int = 20

    # ── Agent ──
    clarify_threshold: float = 0.75
    max_clarify_rounds: int = 3
    max_questions_per_round: int = 5
    max_tool_rounds: int = 10
    agent_timeout: float = 180.0

    # ── 特性开关 ──
    memory_enabled: bool = True
    sandbox_enabled: bool = False
    sandbox_timeout: float = 30.0
    jwt_secret: str = ""
```

---

## 三、from_env() — 环境变量到配置的映射

```python
@classmethod
def from_env(cls):
    c = cls()

    # ── 字符串字段 ──
    for a in ("api_port","api_host","llm_provider","llm_model",
              "pg_host","pg_port","pg_database","pg_user",
              "deepseek_base_url","deepseek_model",...):
        ev = os.getenv(a.upper(), "")
        if ev and hasattr(c, a):
            setattr(c, a, type(getattr(c, a))(ev))

    # ── float 字段 ──
    for a in ("llm_temperature","llm_timeout","agent_timeout",
              "similarity_threshold","sandbox_timeout"):
        ev = os.getenv(a.upper(), "")
        if ev:
            setattr(c, a, float(ev))

    # ── int 字段 ──
    for a in ("max_tool_rounds","rag_top_k","rag_chunk_min",
              "rag_chunk_max","rerank_top_k","rerank_coarse_k",
              "max_questions_per_round","max_clarify_rounds"):
        ev = os.getenv(a.upper(), "")
        if ev:
            setattr(c, a, int(ev))

    # ── 特殊字段 ──
    c.dashscope_api_key = os.getenv("DASHSCOPE_API_KEY","")
    c.deepseek_api_key = os.getenv("DEEPSEEK_API_KEY","")
    c.openai_api_key = os.getenv("OPENAI_API_KEY","")
    c.pg_password = os.getenv("PGSQLPASSWORD","")
    c.jwt_secret = os.getenv("JWT_SECRET","")

    # ── 布尔特性开关 ──
    c.memory_enabled = os.getenv("MEMORY_ENABLED","true").lower() != "false"
    c.sandbox_enabled = os.getenv("SANDBOX_ENABLED","false").lower() == "true"
    c.rerank_enabled = os.getenv("RERANK_ENABLED","true").lower() != "false"

    return c
```

---

## 四、LLM 工厂 — 多 Provider 支持

```python
# core/llm_client.py

_P = {}  # Provider registry

def _reg(name):
    """装饰器注册 Provider。"""
    def d(fn): _P[name] = fn; return fn
    return d


@_reg("dashscope")
def _dashscope(c):
    from langchain_community.chat_models.tongyi import ChatTongyi
    return ChatTongyi(
        model=c.llm_model,              # qwen-plus
        dashscope_api_key=c.dashscope_api_key,
        temperature=c.llm_temperature,
        timeout=c.llm_timeout,
    )


@_reg("deepseek")
def _deepseek(c):
    from langchain_openai import ChatOpenAI
    return ChatOpenAI(
        model=c.deepseek_model,         # deepseek-chat
        api_key=c.deepseek_api_key,
        base_url=c.deepseek_base_url,   # https://api.deepseek.com/v1
        temperature=c.llm_temperature,
        timeout=c.llm_timeout,
    )


@_reg("openai")
def _openai(c):
    from langchain_openai import ChatOpenAI
    return ChatOpenAI(
        model=c.openai_model,           # gpt-4o
        api_key=c.openai_api_key,
        base_url=c.openai_base_url or None,
        temperature=c.llm_temperature,
        timeout=c.llm_timeout,
    )


@_reg("local")
def _local(c):
    from langchain_openai import ChatOpenAI
    return ChatOpenAI(
        model=c.llm_model,
        api_key="not-needed",
        base_url=c.local_llm_url or "http://localhost:8000/v1",
        temperature=c.llm_temperature,
        timeout=c.llm_timeout,
    )
```

---

## 五、Auto 模式 — 自动选择 Provider

```python
def create_model(config_obj):
    r = config_obj.llm_provider.strip().lower()

    # Auto 模式: 按优先级选择第一个可用的 Provider
    if not r or r == "auto":
        for pk, ak in [
            ("dashscope", "dashscope_api_key"),
            ("deepseek", "deepseek_api_key"),
            ("openai", "openai_api_key"),
        ]:
            if getattr(config_obj, ak, None) or os.getenv(ak.upper()):
                r = pk
                break

    if r not in _P:
        raise ValueError(f"Unknown provider: {r}")

    logger.info(f"[LLM] provider={r}")
    return _P[r](config_obj)
```

**优先级**: DashScope > DeepSeek > OpenAI

---

## 六、.env 文件示例

```bash
# ── LLM Provider ──
LLM_PROVIDER=auto
LLM_MODEL=qwen-plus
DASHSCOPE_API_KEY=sk-xxx
# DEEPSEEK_API_KEY=sk-xxx
# OPENAI_API_KEY=sk-xxx

# ── 数据库 ──
PGSQLPASSWORD=your-password

# ── RAG ──
RAG_TOP_K=3
SIMILARITY_THRESHOLD=0.6
RERANK_ENABLED=true

# ── Agent ──
CLARIFY_THRESHOLD=0.75
MAX_CLARIFY_ROUNDS=3
MAX_TOOL_ROUNDS=10

# ── 特性开关 ──
MEMORY_ENABLED=true
SANDBOX_ENABLED=false

# ── JWT ──
JWT_SECRET=your-secret
```

---

## 七、模型在 Agent 中的使用

同一模型实例在多个场景中使用：

```python
# 1. Router — 意图分类
model.ainvoke([SystemMessage(...), HumanMessage(...)])

# 2. Planner — JSON mode
structured_model = model.bind(response_format={"type": "json_object"})
structured_model.ainvoke([...])

# 3. Executor — 工具调用
parallel_model = model.bind_tools(tools, parallel_tool_calls=True)
create_react_agent(model=parallel_model, tools=tools)

# 4. Checkpoint — JSON mode
structured_model.ainvoke([...])

# 5. Reflect — JSON mode
structured_model.ainvoke([...])

# 6. ContextEngine — L2 摘要 + L3 事实提取
model.ainvoke([...])

# 7. SessionMemory — 摘要生成
model.ainvoke([...])

# 8. UserProfile — 画像更新
model.ainvoke([...])
```

---

## 八、embedding 模型

RAG 和记忆系统使用单独的 embedding 模型：

```python
# services/rag_service.py
from langchain_community.embeddings import DashScopeEmbeddings
self._embedding_model = DashScopeEmbeddings(
    model="text-embedding-v4",
    dashscope_api_key=self._api_key,
)
```

> **注意**: embedding 模型固定使用 DashScope text-embedding-v4。这是阿里云百炼的服务，与 LLM provider 无关。

---

## 九、Rerank 模型

```python
# 百炼 qwen3-rerank
# - 120K token 上下文
# - 最多 500 个文档
# - 支持 100+ 语言
# - HTTP API: POST /compatible-api/v1/reranks
```

---

## 十、关键要点

1. **dataclass + from_env()** — 类型安全 + 自动加载
2. **装饰器注册 Provider** — `@_reg("name")` 即可添加新 LLM Provider
3. **Auto 模式** — 按 API Key 可用性自动选择 Provider
4. **同一模型多场景复用** — bind/json mode/tools 都是同一实例的不同配置
5. **embedding 独立** — 固定使用 DashScope text-embedding-v4
6. **特性开关** — MEMORY_ENABLED / SANDBOX_ENABLED / RERANK_ENABLED 可通过环境变量关闭

---

## 十一、系列结束

恭喜你完成了 Alfred Agent 系统的全部 17 篇课程！

**回顾课程索引**:

| # | 课程 | 核心主题 |
|---|------|---------|
| 00 | [架构全景图](00-概述-架构全景图.md) | 整体是什么 |
| 01 | [Agent入口与生命周期](01-Agent入口与生命周期.md) | HTTP → Graph 完整链路 |
| 02 | [图与状态机](02-图与状态机.md) | LangGraph 节点+路由 |
| 03 | [意图路由](03-意图路由.md) | 两阶段分类 |
| 04 | [上下文引擎](04-上下文引擎.md) | L1/L2/L3 三层架构 |
| 05 | [Planner节点](05-Planner节点.md) | 维度提取+契约 |
| 06 | [追问系统](06-追问系统.md) | 动态追问 |
| 07 | [工程规范检查](07-工程规范检查.md) | 三级安全输出 |
| 08 | [多Agent Panel](08-多Agent-Panel.md) | 三立场并行 |
| 09 | [执行节点](09-执行节点.md) | ReAct Agent |
| 10 | [Checkpoint与Reflect](10-Checkpoint与Reflect.md) | 双保险质检 |
| 11 | [RAG系统](11-RAG系统.md) | 混合检索管道 |
| 12 | [记忆系统](12-记忆系统.md) | 跨会话记忆 |
| 13 | [Skills与工具](13-Skills与工具.md) | Skill+Tool 体系 |
| 14 | [任务契约](14-任务契约.md) | SSOT 模型 |
| 15 | [流式输出](15-流式输出.md) | SSE 事件系统 |
| 16 | [配置与LLM工厂](16-配置与LLM工厂.md) | 多Provider管理 |
