# MakeItSmooth TODO

> 最后更新: 2026-07-10

---

## 架构决策（已确认）

| 决策 | 结论 | 原因 |
|------|------|------|
| Agent 范式 | **ReAct** | 多 Agent 协作的基础，所有决策点必须 LLM 推理 |
| 编排引擎 | **LangGraph StateGraph** | 保留，为后续多 Agent 协作 (`Send()`) 做准备 |
| 向量库 | **PostgreSQL + PGVector** | ✅ 已替换。独立 database `makeitsmooth`，与 ChatLab 隔离 |
| 工具数量 | **6 个核心 Tool** | ✅ 已精简。search_kb / search_web / fetch_url / python_exec / add_to_kb / run_shell_preview |
| 缓存 | **Redis** | 暂不做。产品化阶段再加 |
| 意图识别 | **独立 Router 节点** | 先跑轻量 LLM 分类 → 再跑 Planner 提取维度。职责分离 |
| 多 Agent | **Supervisor-Worker** | Orchestrator 拆解任务 → 分发子 Agent → 汇总结果

---

## ✅ 已完成

### 阶段 A: 核心 Agent 化

- [x] `core/llm_client.py` — 多 Provider LLM 工厂 (DashScope/DeepSeek/OpenAI/Local/Auto)
- [x] `core/graph.py` — V2 ReAct Agentic Loop (Planner→Clarify/Execute→Reflector)
- [x] `core/agent.py` — Agent 编排器 + `process_message_stream()` token 流式
- [x] `routers/chat.py` — V1 兼容 + V2 SSE token 流 (通过 `?v=2` 切换)
- [x] `routers/feedback.py` — 用户反馈收集 + 统计 API
- [x] `prompts/system_prompts.py` — Planner/Executor/Reflector + Skills System Prompts
- [x] `prompts/templates.py` — 删除正则维度提取，维度定义 + 追问模板 + 工具函数
- [x] `models/schemas.py` — 新增 TokenEvent/ToolCallEvent 等 streaming 事件模型
- [x] `config.py` — 多 Provider 配置 + Agent 配置 + Sandbox 配置
- [x] `static/js/chat.js` — V2 token 流式渲染 + 反馈按钮
- [x] `static/css/style.css` — 流式动画 + 反馈 UI
- [x] `CLAUDE.md` — 项目文档
- [x] `CAPABILITIES.md` — 能力清单 + 路线图

### 阶段 B1: 核心工具生态

- [x] `tools/search.py` — search_knowledge_base + search_web(Tavily) + fetch_url + search_chat_history
- [x] `tools/code.py` — python_exec 沙箱 (SANDBOX_ENABLED=true 启用)
- [x] `tools/knowledge.py` — add_to_knowledge_base + list_knowledge_sources
- [x] `tools/text.py` — parse_text + compare_texts + summarize_text
- [x] `tools/__init__.py` — 工具注册表 + 按 Skill 的工具映射
- [x] `memory/session_memory.py` — L2 跨会话记忆 (会话摘要向量化 + ChromaDB)
- [x] `memory/user_profile.py` — L3 用户画像 (长期偏好学习)
- [x] `memory/__init__.py` — 记忆系统入口

---

## 🔴 基础设施升级

### 向量库迁移: ChromaDB → PostgreSQL + PGVector

> 与 ChatLab 统一存储，生产就绪

```
Step 1: Docker 确认 PostgreSQL 可用
  复用 ChatLab 的 postgres 容器，新建 makeitsmooth database
  CREATE EXTENSION vector;

Step 2: 新建 services/vector_store.py
  class PGVectorStore:
      async def search(embedding, top_k, filters) → 替换 rag_service.query()
      async def add(chunks, embeddings)         → 替换 rag_service.collection.add()
      async def delete(ids)

Step 3: 改 rag_service.py
  _collection → _vector_store (PGVectorStore 实例)
  query() / ingest() 方法适配 PG 接口

Step 4: 数据迁移脚本
  scripts/migrate_chroma_to_pg.py
  遍历 ChromaDB collection → 逐条写入 PG

Step 5: 配置
  config.py:
    pg_host / pg_port / pg_database / pg_user / pg_password
```

### Redis 集成

> LLM 响应缓存 + 限流计数器 + 会话热数据

```
Step 1: docker-compose.yml 加 redis 服务

Step 2: requirements.txt 加 redis[hiredis]

Step 3: 新建 services/cache.py
  class AgentCache:
      make_key(message, module) → str    # query → 去重 hash
      async get(key) → Optional[dict]    # 查缓存
      async set(key, value, ttl)         # 写缓存
      async invalidate(pattern)          # 清缓存

Step 4: core/agent.py 加缓存层
  process_message() 开头查缓存 → 命中直接返回
  未命中 → 正常流程 → 结束时写缓存

Step 5: 配置
  config.py:
    redis_url: str = "redis://localhost:6379/0"
    cache_ttl: int = 3600
    cache_enabled: bool = True
```

---

## 🔜 待做: Agent 基础能力完善

### B0: 意图识别 Router（新增）

> 替代手动选卡片，LLM 自动分类用户意图

```python
# 新建 core/router.py
async def route_intent(message: str, model) -> Intent:
    """
    一次轻量 LLM 调用 → 判断用户意图
    场景: prompt_optimize | work_plan | info_organize
          | research | code_help | general
    """
```

- [ ] `core/router.py` — Intent Router (轻量 LLM 调用)
- [ ] `core/graph.py` — Planner 之前插入 Router 节点
- [ ] `models/schemas.py` — 新增 Intent 枚举
- [ ] 测试: 6 类意图各 5 个用例 → 准确率 ≥ 90%

### B1: Tools 精简

> 当前 10 个 → 精简为 6 个核心

```
保留:                           删掉:
  search_knowledge_base          search_chat_history  → L2 记忆替代
  search_web (Tavily)            list_knowledge_sources → 管理功能
  fetch_url                      summarize_text       → Agent 本身就能总结
  python_exec                    parse_text           → python_exec 能覆盖
  add_to_knowledge_base          compare_texts        → 同上
  run_shell_preview  ← NEW(只读)
```

- [ ] 加 `run_shell_preview` tool — 只读命令白名单: ls / cat / head / git log / git status / tree / wc
- [ ] 从 `ALL_TOOLS` 移除搜索/文本处理的 4 个冗余工具
- [ ] 更新 `tools/__init__.py` 的 ALL_TOOLS 列表

### B2: Graph 集成新工具

### B2: Graph 集成新工具

- [ ] `core/graph.py` — execute_node 使用新工具集 (当前仍用旧 ALL_TOOLS)
- [ ] `core/agent.py` — 注入 SessionMemory / UserProfile 到图中
- [ ] `core/agent.py` — 会话结束自动触发 summarize_and_store
- [ ] `core/agent.py` — 会话开始自动检索历史上下文 + 用户画像

### B3: 后端增强

- [ ] Tavily API 测试 (需要 TAVILY_API_KEY)
- [ ] python_exec 沙箱安全性审查 (当前禁文件写/网络/shell, 需验证逃逸)
- [ ] 工具调用超时 + 错误重试策略统一
- [ ] ChromaDB 多 collection 管理 (session_memory + user_profile + domain_knowledge)

### B4: 前端适配

- [ ] 首页从三卡片改为统一对话入口 (自由输入 + 快捷能力标签)
- [ ] 拖拽粘贴文本/代码到聊天框 (不用本地文件系统)
- [ ] token 流式渲染中的 tool_start/tool_end 状态展示
- [ ] 反馈按钮联动 (提交后显示状态)

---

## 🔮 之后: Token 后台检测

> 自己实现，AI 引导

### 1. Token 用量实时监控

- [ ] `obs/token_tracker.py` — 每次 LLM 调用的 token 计数回调
- [ ] 前端显示: "本次对话: 1,247 tokens · 预估费用 ¥0.003"
- [ ] 按 session / 按日 / 按月 统计
- [ ] Token 超限预警 (用户设置月度预算)
- [ ] 降级策略: 超出预算自动切便宜模型 (qwen-plus→qwen-turbo)

### 2. 思考链 (Chain-of-Thought) 可视

- [ ] Agent 在 ReAct 循环中暴露 "思考过程"
- [ ] WebUI 可折叠的 "查看推理过程"
- [ ] 每次 tool call 记录: 为什么选这个工具？输入参数怎么决定的？

### 3. 上下文窗口管理

- [ ] 检测当前 messages 的总 token 数
- [ ] 接近窗口上限时自动: 压缩旧消息 / 摘要旧消息 / 警告用户
- [ ] 模型自适应: 检测到长上下文需求 → 自动切到更大窗口的模型

---

## 🔮 之后: 幻觉检测

> 自己实现，AI 引导

### 1. 事实性校验

- [ ] 输出中的断言（"XX 是 YY"）→ search_web 交叉验证
- [ ] 引用标注: 每个事实声明必须标注来源
- [ ] 矛盾检测: 输出内容自相矛盾时标记

### 2. 置信度分层

- [ ] 高置信: 知识库检索到 + 多源交叉验证 → 直接输出
- [ ] 中置信: 检索到部分信息 → 标注 "据知识库..."
- [ ] 低置信: 纯 LLM 生成，无法验证 → 标注 "以下为 AI 推测，未经核实"

### 3. 幻觉报告

- [ ] 每次输出附 "可信度报告": 几个声明被验证 / 几个无法验证
- [ ] 用户标记某段话是幻觉 → 自动写入反馈 → 调整后续输出

---

## 🔮 之后: 循环检测

> 自己实现，AI 引导

### 1. ReAct 循环检测

- [ ] 相同 tool + 相同参数连续调用 > 2 次 → 打断
- [ ] 循环总轮数 > max_tool_rounds → 强制输出当前最佳结果
- [ ] "来回摇摆" 检测: Agent 在两个方案间反复切换

### 2. 追问循环检测

- [ ] 追问超过 MAX_CLARIFY_ROUNDS(5) 且信息无进展 → 停止追问直接执行
- [ ] 用户连续回答 "不知道" / "随便" → 跳过该维度

### 3. 输出循环检测

- [ ] Reflector 连续两次 reject → 不再重试，直接输出并标注
- [ ] 输出内容重复度检测 (与上次输出文本相似度 > 80% → 警告)

---

## 🔮 RAG 语义化分块（之后自己做）

> 需要我引导的部分

### 当前分块问题

`services/rag_service.py:_chunk_text()` — 按 `## ` 标题 + 句子分块:
- 固定大小 500 字符，不考虑语义边界
- 分块之间 overlap=50，但不保证语义完整
- 没有 metadata 丰富化（来源、类型、难度标签）

### 计划升级方向

1. **语义分块**: 用 embedding 相似度变化检测自然段落边界
2. **层级上下文**: 每 chunk 带上父标题 (H1→H2→H3 链)
3. **Chunk 策略路由**: 代码块用 AST 分块，文章用段落分块，API 文档用函数签名分块
4. **重排序**: 检索后用 Cross-Encoder 重排 top-K
5. **混合检索**: BM25 (关键词) + 向量 (语义) 融合

### 实现步骤（你来做，我引导）

1. 先分析现有 `_chunk_text()` 的问题场景
2. 我解释语义分块原理 → 你实现
3. 我提供测试用例 → 你验证
4. 对比旧分块 vs 新分块的检索准确率

---

## 📋 实施优先级

```
P0 (本周) ─────────────────────────────────────────────
  B0: 意图识别 Router
  B1: Tools 精简 (6 个核心)
  B2: Graph 集成新工具 + 记忆注入

P1 (下周) ─────────────────────────────────────────────
  Redis 集成 (LLM 缓存)
  PGVector 迁移 (向量库)
  Token 用量实时监控 (你主导)

P2 (下下周) ───────────────────────────────────────────
  幻觉检测基础版 (你主导)
  循环检测 (你主导)
  B4: 前端统一对话入口

P3 (后续) ─────────────────────────────────────────────
  RAG 语义化分块 (你主导, 我引导)
  多 Agent 协作 (LangGraph Send API)
  产品化 (认证/限流/LangFuse)
```

---

## 📜 项目文件导航

| 文件 | 读者 | 内容 |
|------|------|------|
| [GOVERNANCE.md](GOVERNANCE.md) | 开发者 | **项目宪章**: 开发原则、代码审查、安全规范、质量指标、多Agent协议 |
| [CLAUDE.md](CLAUDE.md) | 开发者 | 架构、启动、开发指南 |
| [CAPABILITIES.md](CAPABILITIES.md) | 产品/开发者 | 能力清单、API Key矩阵 |
| [TODO.md](TODO.md) | 所有人 | 本文件，待做事项 |

**修改 Agent 行为前必须查阅 GOVERNANCE.md。**
