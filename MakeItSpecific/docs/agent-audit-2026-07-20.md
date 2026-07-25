# MakeItSpecific Agent 审计报告

> 2026-07-20 | 基于 V3 架构的全面审计

## 总体评价

**个人项目中的高质量 Agent，架构设计优秀，但距企业级生产标准尚有 4 个维度的显著差距。**

在 RAG 管道和上下文管理两个维度已达到或接近企业水平。从「能跑的 Agent demo」到「生产级 Agent 服务」，差的是**可观测性、评估体系、安全性和可靠性**——这些不是算法问题，是工程基础设施问题。

---

## 目录

1. [项目做得好的地方](#1-项目做得好的地方)
2. [欠缺什么 — 按严重程度排序](#2-欠缺什么)
3. [额外发现：代码/文档不一致](#3-额外发现代码文档不一致)
4. [市面上企业 Agent 产品长什么样](#4-市面上企业-agent-产品长什么样)
5. [差距量化](#5-差距量化)
6. [优先级行动清单](#6-优先级行动清单)

---

## 1. 项目做得好的地方

### 1.1 架构设计

| 维度 | 具体实现 | 评价 |
|------|---------|------|
| **图结构** | LangGraph `StateGraph` 8 节点：Router → Enrich → RAG → Planner → Clarify/Execute → Checkpoint → Reflect | 节点职责清晰，条件路由合理 |
| **三层上下文** | L1 滑动窗口(最近3轮原文) + L2 滚动摘要(LLM增量更新) + L3 语义事实(PGVector持久化) | 比大多数开源 Agent 的上下文管理都更用心 |
| **混合 RAG** | Dense(PGVector) + BM25(tsvector+GIN) → RRF融合 → qwen3-rerank精排 → 相似度过滤 → 关键词加权 | 5步管道，达企业级水平 |
| **语义分块** | `SemanticChunker` — 相邻句子 embedding 相似度断崖切分 | 自研，优于固定大小分块 |
| **意图路由** | LLM 精判 + 规则快检双层 fallback，confidence < 0.8 自动升级 | 兼顾准确率和延迟 |
| **多 Provider** | DashScope / DeepSeek / OpenAI / Local 四套 LLM 统一工厂，auto 模式自动检测可用 provider | 实用且健壮 |
| **记忆系统** | SessionMemory(会话摘要向量化) + UserProfile(用户画像提取)，PGVector持久化，跨会话可用 | 设计完整 |

### 1.2 工程细节

- **错误降级链完整**：LLM 失败 → 规则兜底 → 默认值，不抛异常阻断流程（全局 15+ 个降级点）
- **JSON 解析健壮**：处理 markdown 代码块包裹、模型额外文本，3 层 fallback（直接解析 → 提取代码块 → 正则提取花括号）
- **SSE 流式输出**：session → tool_start/tool_end → clarify/execute → done 事件流
- **PG 全栈**：会话/消息/反馈/知识库/向量/用户画像全走 PostgreSQL，告别 SQLite
- **架构文档**：`boundary.md` 7维度约束规范 + 检查清单 + 注意力层级 🔴🟡🟢⚪ 设计
- **工具 docstring**：5个工具全部遵循三段式标注（用途/不要用/优先级/参数返回/限制）
- **优雅降级启动**：`lifespan` 中即使初始化失败，app 仍启动以便健康检查和静态文件可用

---

## 2. 欠缺什么

### 🔴 Tier 1：投产前必须解决

#### 2.1 可观测性：几乎为零

**当前状态：** 仅 Python logging + RotatingFileHandler（stdout + 文件双写，5MB×3）

**缺失清单：**

| 缺失项 | 说明 | 影响 |
|--------|------|------|
| **全链路 Tracing** | 看不到每次请求在 8 个节点间的耗时分布、LLM 调用了多少次 | 无法定位性能瓶颈 |
| **Token 用量追踪** | `_estimate_input_tokens()` 是 `字符数/2.5` 的粗略估计，不追踪 output token | 无法核算成本 |
| **成本核算** | 不知道每次对话花了多少钱 | 无法控制预算 |
| **Metrics** | 无 QPS、P50/P99 延迟、工具调用成功率、Reflector 驳回率 | 无法评估服务质量 |
| **Alerting** | Agent 超时/工具死循环/LLM 全部不可用时无人知晓 | 故障发现靠用户投诉 |

**推荐方案：** 接入 LangFuse（开源，Python SDK 一行代码集成），覆盖所有 LLM call 和 tool call 的 latency + token + cost 埋点。

#### 2.2 评估体系：仅 25 个纯函数单测

**当前状态：**

```
tests/test_graph.py:    25 tests — 只测 _merge_dimensions_from_plan / _parse_planner_json 等纯函数
tests/test_session_store.py: 5 tests — PG 集成测试（需 PG 环境）
```

**缺失清单：**

| 缺失项 | 说明 |
|--------|------|
| **集成测试** | 从未真正跑过一次完整的 `graph.ainvoke()` 并验证输出 |
| **E2E 测试** | 从未通过 SSE 发一条消息并验证完整事件流 |
| **回归测试集** | `boundary.md` 第3节定义了 badcase 体系但 `tests/badcase_regression.jsonl` **不存在** |
| **LLM-as-Judge 评估** | 没有用强模型自动评估输出质量的 pipeline |
| **RAG 召回率测试** | 不知道知识库检索的 recall@k 是多少 |

**推荐方案：** 先收集 50-100 条 golden cases（你实际使用中遇到的典型输入+期望输出），建 CI 自动评估，每次改 prompt 或模型后跑一遍。

#### 2.3 安全性：基本裸奔

| 问题 | 说明 | 风险 |
|------|------|------|
| **CORS 全开** | `allow_origins=["*"]` | 任何网站可调用你的 API |
| **无身份认证** | 任何人可调 `/api/chat/stream` | 无 API Key 验证，无用户认证 |
| **无速率限制** | 可无限频率调用 | 消耗 LLM 费用 |
| **无输入验证** | Pydantic 只做类型校验 | 不做内容安全检查（注入/PII） |
| **无输出过滤** | LLM 输出直接返回 | 无 PII 检测、无有害内容过滤 |
| **`shell=True` 风险** | `run_shell_preview` 用了 `shell=True` | 虽有白名单缓解，仍是不良实践 |
| **`python_exec` 沙箱不明确** | `sandbox_enabled=False` 默认关闭 | 即使开启，安全边界也不清晰 |

**推荐方案：**
1. 加 API Key 中间件（FastAPI middleware，1小时工作量）
2. 收紧 CORS 到域名白名单
3. 加 slowapi 做速率限制（10分钟工作量）

#### 2.4 可靠性：单点脆弱

| 问题 | 说明 | 影响 |
|------|------|------|
| **LLM 调用无显式重试** | 网络抖动一次就失败 | 依赖 LangChain 内置重试（不可见/不可控） |
| **无熔断器** | LLM 持续超时时每个请求都等 `agent_timeout=180s` | 雪崩 |
| **无请求队列/背压** | 高并发时无保护 | 资源耗尽 |
| **ContextEngine 状态在内存** | `_running_summary` 在进程内存中 | 重启丢失、无法水平扩展 |
| **无优雅关闭** | `lifespan` 只关 DB 连接 | in-flight agent 执行被暴力中断 |

**推荐方案：**
1. `tenacity` 库加 LLM 重试（30分钟）
2. `_running_summary` 外移到 Redis（2天）
3. 信号处理 + in-flight 请求等待（半天）

---

### 🟡 Tier 2：重要缺失（影响规模化）

#### 2.5 Multi-Agent 能力：仅单 Agent

当前只有一个 ReAct loop。`boundary.md` 提到 `delegate_task`，但已在 `tools/__init__.py` 中删除：

```python
# 删除 delegate_task — 子 Agent 只有 search_kb 无额外价值，executor 自身已覆盖
```

**企业 Multi-Agent 的典型模式：**

- **Supervisor-Worker**：一个路由 Agent 分发任务给专业子 Agent（Coder / Researcher / Writer / Reviewer）
- **Agent 团队协作**：Code Review Agent + Test Writer Agent + Doc Writer Agent 并行工作后汇总
- **Human-in-the-Loop**：关键决策（如删除数据、发送消息、修改生产配置）需人工审批

#### 2.6 Prompt 管理：硬编码在 Python 中

```python
# prompts/system_prompts.py — 所有 prompt 都是 Python 字符串常量
PLANNER_SYSTEM_PROMPT = """..."""
EXECUTOR_SYSTEM_PROMPT = """..."""
REFLECTOR_SYSTEM_PROMPT = """..."""
```

**问题：**
- 改 prompt 需要改代码 + 重新部署（不能热更新）
- 无法 A/B 测试两个 prompt 版本
- 没有 prompt 变更历史记录
- 非技术人员无法调整 prompt

**推荐方案：** 短期用 YAML/JSON 文件 + 热加载；长期用 LangFuse Prompt Management。

#### 2.7 Agent-as-Tool / 工具生态薄弱

当前 5 个工具全部是本地操作。企业 Agent 通常具备：

- **API 连接器**：Slack、Jira、GitHub、Google Calendar、Notion 等 SaaS 工具
- **数据库查询**：直接查业务 DB 做数据分析
- **代码仓库操作**：创建 PR、Review 代码、合并分支
- **可扩展的工具注册机制**：插件式注册（非硬编码 import）

#### 2.8 缓存层缺失

| 缺失 | 影响 |
|------|------|
| **RAG 结果缓存** | 同一个 query 每次都重新 embedding + 检索 + rerank |
| **LLM 响应缓存** | 相似问题每次都重新调 LLM |
| **Embedding 缓存** | 知识库文件未修改时仍重新生成 embedding |

#### 2.9 Streaming 实际未达到 token 级

`agent.py` 第 215-220 行有明确注释：

```python
# astream_events 只能捕获外层图节点的 LLM 事件（planner/router 等），
# execute_node 内部 create_react_agent 是子图，其 token 不会冒泡上来。
# 因此用 ainvoke 拿最终结果，再由 SSE 事件一次性推送完整输出。
```

这意味着 **V2 的「token 级流式」标签名不副实**——前端 `chat.js` 虽然写了逐 token 渲染逻辑，但后端实际是等整个图跑完才推送完整结果。要解决这个问题需要重构 execute_node，改用 `stream_mode="messages"` 或在子图上调用 `astream_events`。

---

### 🟢 Tier 3：锦上添花

- **多模态输入**：不支持图片、PDF、语音
- **会话分支**：不能从某一轮 fork 出替代方案
- **Slack/飞书 Bot 集成**：只有 HTTP API，无 IM 接入
- **国际化**：仅中文
- **结构化输出保证**：大量依赖 LLM JSON mode 但无 schema validation 兜底
- **Prompt 注入防护**：用户消息直接拼入 prompt 模板，无任何清洗

---

## 3. 额外发现：代码/文档不一致

Explore Agent 在全面审计中发现了以下文档与代码的偏差：

| 文档声称 | 实际代码 | 严重程度 |
|---------|---------|---------|
| CLAUDE.md: Skills 用 YAML 注册 | `Agent.__init__()` 中硬编码 Python 类实例化 | 中 |
| CLAUDE.md: 用 SQLite 存会话 | 实际用 PostgreSQL (`SessionStore`) | 低（升级了但没更新文档） |
| CLAUDE.md: 7个工具（含 delegate/search_web 等） | `tools/__init__.py` 中 5 个工具，7个已删除 | 中 |
| CLAUDE.md: Token 级流式 | `agent.py` 注释说明子图 token 不冒泡，实际是一次性推送 | 高 |
| README: 本地 :8000 | Docker compose 用 :8000，config 默认 :8001 | 低 |
| boundary.md: delegate_task 约束 | delegate_task 已从代码中删除 | 低 |

**此外：**
- Skills 在 execute_node 中被绕过——execute_node 用 `create_react_agent()` 直接创建 ReAct agent，只在 ReAct 无输出时才 fallback 到 `_execute_legacy_skill()`，意味着 skill 实例大部分时候是死代码
- `config.py` 的 `from_env()` 读 `.env` 路径为 `Path(__file__).resolve().parent.parent / ".env"`（MakeItSpecific 的上级目录），看起来是期望 `.env` 在 portal 根目录

---

## 4. 市面上企业 Agent 产品长什么样

### 4.1 主流企业 Agent 架构（2025-2026）

```
                        ┌──────────────┐
                        │  API Gateway │  ← Auth / Rate Limit / Routing
                        └──────┬───────┘
                               │
                    ┌──────────┴──────────┐
                    │   Agent Runtime     │
                    │  ┌──────────────┐   │
                    │  │ Orchestrator │   │  ← Plan → Execute → Verify loop
                    │  └──────┬───────┘   │
                    │         │           │
                    │  ┌──────┴───────┐   │
                    │  │ Tool Gateway │   │  ← 30+ managed tools, access control
                    │  └──────┬───────┘   │
                    └─────────┼───────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        │                     │                     │
   ┌────┴────┐          ┌────┴────┐          ┌────┴────┐
   │ Memory   │          │  RAG    │          │ Guard   │
   │ (Redis+  │          │ (Multi- │          │ (Input/  │
   │  PGVector│          │  Source)│          │  Output) │
   └─────────┘          └─────────┘          └─────────┘
```

### 4.2 代表性产品对比

| 产品 | 定位 | 核心差异 |
|------|------|---------|
| **LangGraph Cloud** | Agent 部署平台 | 托管 LangGraph 图、内置 Tracing、Cron Jobs、Human-in-Loop、Horizontal Scaling |
| **CrewAI** | Multi-Agent 框架 | Role-based Agent、Agent 间共享记忆、顺序/层级执行模式 |
| **AutoGen (Microsoft)** | Multi-Agent 对话 | Agent Chat 模式、代码生成+执行循环、人机协作 |
| **Agno** | 轻量 Agent 框架 | 极简 API、内置 Memory/Knowledge/Tools、30+ Model Provider |
| **企业内部自研** | 定制 Agent 平台 | 通常基于 LangGraph + 自研 Tool Gateway + 企业 SSO + 审计合规 |

### 4.3 企业级 Agent 的硬性要求

1. **全链路 Tracing**（OpenTelemetry + LangFuse/LangSmith）— 100% 覆盖 LLM call + tool call
2. **自动化评估 Pipeline** — 每次 deploy 前在 golden dataset 上跑 eval，分数下降则阻止上线
3. **Prompt CI/CD** — prompt 和代码一样走 review → test → canary → full deploy
4. **网关层** — Auth (SSO/OAuth/API Key) + Rate Limit + 审计日志
5. **Guardrails** — Input guard (注入检测/PII) + Output guard (有害内容/幻觉检测/格式校验)
6. **成本可控** — 每次调用有 token budget，超过走降级模型链
7. **SLA 保障** — 99.9% uptime、p99 < 30s、自动扩缩容
8. **多租户隔离** — 每个租户独立的 memory/RAG namespace、独立的 rate limit 和 cost counter

---

## 5. 差距量化

```
维度              MakeItSpecific        企业级要求              差距           优先级
──────────────────────────────────────────────────────────────────────────────────
可观测性          日志+文件轮转           全链路 Tracing+Metrics   🔴 从零建       P0
评估体系          25单测+5集成测          自动化 Eval Pipeline     🔴 从零建       P0
安全              CORS全开+无鉴权         SSO+Guardrails          🔴 从零建       P1
可靠性            无重试/无熔断           多层容错+HA              🔴 从零建       P1
Multi-Agent      无                      Supervisor 模式         🟡 架构大改     P2
Prompt 管理       Python 硬编码           版本化+热更新            🟡 架构改动     P2
工具生态          5个本地工具             30+外部连接器            🟢 增量建设     P3
缓存             无                      Redis 多层缓存           🟢 增量建设     P3
──────────────────────────────────────────────────────────────────────────────────
架构设计          V3三层上下文             业界中上水平             🟢 已有基础     —
RAG 管道          混合检索+Rerank         业界先进水平             ✅ 已达标准     —
上下文管理        L1+L2+L3三层            业界先进水平             ✅ 已达标准     —
降级策略          15+ 降级点              生产级                   ✅ 已达标准     —
```

---

## 6. 优先级行动清单

按投入产出比排序，假设单人开发：

### Phase 1：打好基础（1-2周）

| # | 事项 | 工作量 | 说明 |
|---|------|--------|------|
| 1 | **接入 LangFuse Tracing** | 1天 | 所有 LLM call + tool call 自动埋点，可视化 latency/token/cost |
| 2 | **加 API Key 认证** | 半天 | FastAPI middleware，读 `X-API-Key` header |
| 3 | **加速率限制** | 半天 | `slowapi` 库，每 IP 每分钟 20 次 |
| 4 | **加 LLM 重试** | 半天 | `tenacity` 包装 `model.ainvoke()`，指数退避，最多 3 次 |
| 5 | **加熔断器** | 半天 | LLM 连续失败 5 次 → 熔断 30 秒 → 半开探测 |
| 6 | **修复 Prompt 注入** | 半天 | 用户消息用 XML tag 包裹 `<user_message>...</user_message>`，与系统指令隔离 |

### Phase 2：建立评估（2-3周）

| # | 事项 | 工作量 | 说明 |
|---|------|--------|------|
| 7 | **收集 Golden Dataset** | 3天 | 50-100 条实际使用的输入+期望输出 |
| 8 | **搭建 Eval Pipeline** | 2天 | GPT-4 做 judge，自动评分，CI 集成 |
| 9 | **建 Badcase 回归** | 1天 | 实现 `boundary.md` 定义的 badcase 自动收集和回归测试 |
| 10 | **补充集成测试** | 2天 | 真正跑 `graph.ainvoke()` 并验证输出包含关键内容 |

### Phase 3：架构加固（3-4周）

| # | 事项 | 工作量 | 说明 |
|---|------|--------|------|
| 11 | **实现真正的 token 级流式** | 2天 | 重构 execute_node，用 `stream_mode="messages"` 捕获子图 token |
| 12 | **ContextEngine 状态外移 Redis** | 2天 | `_running_summary` 从内存移到 Redis，实现水平扩展 |
| 13 | **Prompt 外置化** | 2天 | 所有 prompt 移入 `prompts/*.yaml`，支持热加载 |
| 14 | **加 Guardrails** | 1天 | Input: 注入检测 + PII 过滤；Output: 有害内容检测 |
| 15 | **修复代码/文档不一致** | 1天 | 更新 CLAUDE.md / README 对齐实际代码状态 |

### Phase 4：规模化（长期）

| # | 事项 | 工作量 | 说明 |
|---|------|--------|------|
| 16 | Multi-Agent 架构 | 1-2周 | Supervisor-Worker 模式，子 Agent 分工协作 |
| 17 | RAG 缓存层 | 3天 | Redis 缓存 embedding + 检索结果 |
| 18 | 工具生态扩展 | 持续 | GitHub/GitLab/Slack 连接器 |
| 19 | Prompt CI/CD | 1周 | prompt 版本化 + A/B test + 自动上线 |
| 20 | 多租户 | 1周 | 租户隔离的 memory/RAG/cost 命名空间 |

---

## 附录 A：技术债务速查

| 位置 | 问题 | 修复建议 |
|------|------|---------|
| `routers/chat.py` | SSE 流式标签不实 | 用 `stream_mode="messages"` 捕获子图 token |
| `core/agent.py:220` | 子图 token 不冒泡 | LangGraph 新版本可能已支持，升级验证 |
| `tools/shell.py` | `shell=True` | 改用 `shell=False` + 列表参数 |
| `config.py:8` | `.env` 路径读上级目录 | 确认是否正确，可能是 portal 层设计的 |
| `app.py:100` | CORS `*` | 改为环境变量配置的域名白名单 |
| `skills/*.py` | 大部分是死代码 | 要么集成进 execute_node，要么删除 |
| `CLAUDE.md` | 多处与实际代码不一致 | 全文审计并更新 |
| `Dockerfile` | EXPOSE 8000 vs config 8001 | 统一端口号 |

---

*本报告基于 2026-07-20 对 `MakeItSpecific` V3 代码库的完整审计。*
