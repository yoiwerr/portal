# MakeItSpecific — 项目总结

> AI 工作流增强 Agent · 把模糊想法变成可执行方案
> 个人项目 · 2026-06 ~ 至今

---

## 一句话定位

**LangGraph ReAct Agent + 生产级 RAG + 三层记忆系统 + 精简化工具生态** — 通过引导式对话与工具调用，将用户的模糊需求转化为结构化输出（优化提示词 / 工作计划 / 信息文档 / 代码审查报告）。

---

## 技术栈

| 层级 | 技术选型 | 说明 |
|------|---------|------|
| **Web 框架** | FastAPI + SSE (sse-starlette) | token 级流式输出 |
| **Agent 引擎** | LangGraph StateGraph + create_react_agent | 8 节点有状态图 |
| **LLM Provider** | DashScope (Qwen) / DeepSeek / OpenAI / Local | 装饰器注册模式，auto 自动选 |
| **向量存储** | PostgreSQL + PGVector (pg16) | IVFFlat 索引 + GIN 全文检索 |
| **Embedding** | DashScope text-embedding-v4 (1024维) | 与 ChatLab 共用 |
| **Rerank** | 百炼 qwen3-rerank | Cross-Encoder 精排 |
| **会话存储** | PostgreSQL (psycopg 3) | sessions + messages + feedback 表 |
| **前端** | Vanilla HTML/CSS/JS | 暗色主题，SSE token 流式渲染 |
| **部署** | Docker Compose + nginx 反代 | 与 ChatLab 共用 PG 容器 |

---

## 架构全景

```
Browser (SSE Token Streaming)
  │ POST /api/chat/stream?v=2
  ▼
┌─────────────────────────────────────────────────────────┐
│                   Agent 编排层                            │
│                                                          │
│  START → Router → Enrich → RAG → Planner                │
│                                      ├─ Clarify → END    │
│                                      └─ Execute (ReAct)  │
│                                            │              │
│                                      Checkpoint           │
│                                        ├─ 偏移 → Execute  │
│                                        └─ 对齐 → Reflect  │
│                                            ├─ pass → END  │
│                                            └─ retry(≤2)   │
└─────────────────────────────────────────────────────────┘
        │              │              │              │
   ┌────▼───┐   ┌─────▼────┐  ┌─────▼────┐  ┌─────▼──────┐
   │ Router │   │ Context  │  │  Memory  │  │   Tools    │
   │ LLM+规则│   │ Engine   │  │  L2 + L3 │  │    (×5)    │
   │ 6→4场景│   │ L1+L2+L3 │  │ PGVector │  │ 精简化设计  │
   └────────┘   └─────┬────┘  └──────────┘  └─────┬──────┘
                      │                            │
          ┌───────────▼──────────────┐   ┌─────────▼─────────┐
          │   RAG 混合检索管道        │   │   4 个 Skill       │
          │  Dense + BM25 → RRF      │   │ prompt_refiner     │
          │  → qwen3-rerank → 过滤   │   │ work_arranger      │
          │  SemanticChunker 分块    │   │ info_retention     │
          └──────────────────────────┘   │ code_review        │
                                         └───────────────────┘
          ┌──────────────────────────────────────────────────┐
          │           存储层 (PostgreSQL)                      │
          │  domain_knowledge · session_memory · user_profile │
          │  sessions · messages · feedback                   │
          └──────────────────────────────────────────────────┘
```

### 8 个图节点职责

| # | 节点 | 触发条件 | 功能 | LLM 调用 |
|---|------|---------|------|:---:|
| 1 | **Router** | module="auto" | LLM + 规则双通道意图分类，6 种场景 → 4 个 Skill | 1 (规则置信度低时) |
| 2 | **Enrich** | 始终 | ContextEngine 预构建的增强 query 透传 | 0 |
| 3 | **RAG** | 首次 | Dense+BM25→RRF→Rerank 混合检索知识库 | 3 API (embed+rerank+batch) |
| 4 | **Planner** | 始终 | LLM JSON mode 维度提取 + 完整度判断 + 生成追问/执行计划 | 1 |
| 5 | **Clarify** | 完整度 < 阈值 | 格式化追问消息，一性问 4-5 题 | 0 (规则) |
| 6 | **Execute** | 完整度 ≥ 阈值 | ReAct tool calling loop，按 Skill 暴露 2-4 工具 | N (ReAct rounds) |
| 7 | **Checkpoint** | Execute 完成后 | 语义对齐检查 — 方向对不对（比 Reflector 快） | 1 |
| 8 | **Reflector** | Checkpoint 通过后 | 质量审核 — 完整性/准确性/忠实度/可用性/格式 | 1 (score<7 时最多 2 次) |

---

## 工具系统 — 5 个工具，零重叠

核心设计理念：**tool 不是越多越好。每个 tool 有明确的 "什么时候用 / 坚决不用 / 与其他 tool 的关系" 三段式标注。**

| # | 工具 | 类型 | 存储 | Skill 可见 |
|---|------|------|------|-----------|
| 1 | **search_knowledge_base** | 读（知识库） | PGVector → 结构化 JSON | 全部 4 个 Skill |
| 2 | **add_to_knowledge_base** | 写（知识库） | PGVector，async，30 字门槛 | 全部 4 个 Skill |
| 3 | **run_shell_preview** | 读（文件系统） | 白名单 9 命令，10s 超时 | work_arranger, code_review |
| 4 | **write_file** | 写（文件系统） | data/exports/，路径穿越拦截 | info_retention, work_arranger |
| 5 | **python_exec** | 执行 | 沙箱隔离命名空间，默认关闭 | (全局，SANDBOX_ENABLED 门控) |

**从 12 个精简到 5 个的砍削过程**：删除 search_web / fetch_url（联网搜索，不在定位内）、delegate_task（子 Agent 与 Executor 重叠）、search_chat_history（ContextEngine 已自动注入历史）、parse_text / compare_texts / summarize_text（规则引擎，LLM 原生更优）、list_knowledge_sources（运维操作不是对话工具）。

**并行调用**：Executor prompt 含并行规则 — 互不依赖的工具调用可以同一轮同时发出（如 search_knowledge_base + run_shell_preview），减少串行轮数。

**结构化输出**：search_knowledge_base 返回 JSON 而非 Markdown：
```json
{"hit": true, "results": [{"rank": 1, "source_file": "rag-deep-dive.md", "score": 0.92}], "total_scanned": 20}
```
LLM 可直接解析 source_file 做引用、score 做置信度判断、hit 做覆盖判断 — 不需要从 Markdown 中提取。

---

## RAG 检索管道

```
用户 query
  │
  ├─ 1. ContextEngine query 增强（短 query 加 L3 事实 + dims）
  │
  ├─ 2. SemanticChunker 语义分块（相邻句子 embedding 相似度断崖切分）
  │     knowledge_base/*.md → 200-800 字符 chunk
  │     DashScope text-embedding-v4 → 1024 维向量
  │
  ├─ 3. 混合检索 (Hybrid Search)
  │     Dense:  PGVector cosine (<＝> 算子), IVFFlat 索引, top-20
  │     Sparse: PG tsvector GIN 索引, plainto_tsquery('simple'), top-20
  │
  ├─ 4. RRF 合并 (Reciprocal Rank Fusion, k=60)
  │
  ├─ 5. Rerank: 百炼 qwen3-rerank Cross-Encoder 精排, top-20 → top-5
  │
  ├─ 6. 过滤: 相似度 ≥ 0.6 (dense) 或 rerank_score ≥ 0.3
  │
  └─ 7. 关键词重叠加权（技术术语匹配 +0.05 score）
```

**分块去重**：按 content_hash (MD5) 检查 `exists_by_metadata()`。改过的文件不重复索引，新增的自动索引。每次 make dev 启动，无文件变更时零 embedding API 调用。

---

## 三层记忆系统

### ContextEngine — 单会话内记忆

| 层 | 粒度 | 时间范围 | 更新频率 | 成本 | 注入位置 |
|----|------|---------|---------|------|---------|
| **L1** 原始窗口 | 完整原文 | 最近 3 轮 | 每轮追加 | 零 LLM | Planner + Executor prompt (🟡) |
| **L2** 滚动摘要 | 压缩摘要 | 全部历史 | 每轮增量更新 | 1 LLM (≈500 tokens) | Planner + Executor prompt (🔴 最高优先级) |
| **L3** 语义事实 | 原子事实 | 全部历史 | 每轮 LLM 提取 | 1 LLM (≈600 tokens) | Planner + Executor prompt (🟢) |

**L2 增量更新公式**：`新 L2 = LLM(旧 L2 + 本轮对话)` — O(1) 成本无论历史多长。

**主题切换检测**：当前消息关键词 vs L2+L3 关键词重叠率 = 0 → 重置 L2 + 清空 L3，旧话题不污染新话题。

**L3 双路径**：LLM JSON mode 结构化提取 6 种分类（偏好/决策/约束/技术栈/目标/其他）→ 主路径 PGVector 语义检索，后备内存关键词匹配。置信度标注。

### SessionMemory — 跨会话记忆

会话完成时 **一次性** LLM 摘要 → JSON `{title, summary, decisions, tech_stack, projects, todos, tags}` → embedding → PGVector session_memory 表。新会话开始时向量检索 top-3 历史 → 注入为 🧠 上下文。

### UserProfile — 长期画像

**双层更新**：规则层快速合并 tech_stack/projects（新出现 confidence=0.5，复用+0.1，上限 1.0）+ LLM 层智能推断 domain/work_style。单文档储存在 PGVector user_profile 表。新会话开始时注入为 👤 上下文。

---

## 意图识别与工作记忆

### 已锁定意图（解决意图偏移）

在 Planner 和 Executor 的 System Prompt **最前面** 注入 🔴 锁定块：

```
## 🔴 已锁定意图（最高优先级，不可偏离）
- **当前任务**: 代码审查
- **置信度**: 90%
- **规则**: 以下所有回答必须围绕此意图。
```

Executor 的反思关 1 直接引用此块 — 不依赖模糊的 "用户原始消息"。

### 工作记忆（解决信息遗忘）

与锁定意图并列注入 🔴 工作记忆：

```
## 🔴 工作记忆（已确认的需求信息，跨轮持久化，不会丢失）
- ✅ **target_files**: main.py
- ✅ **focus_areas**: 安全性
```

文案直接告诉 LLM "跨轮持久化，不会丢失" — 这是锁定的，不是可选上下文。

### 追问优化

一性问 4-5 个问题（从 2-3 提升），追问轮数从 5 降到 3。追问消息从 ~15 行缩减到 ~6 行 — 删除 "我问这个是因为…" 解释、hint 提示词、RAG 备注。

---

## 反思内化 (Reflection-in-the-Loop)

**0 额外 LLM 调用**。Executor 每一步 Think 自动过三关：

| 关 | 自问 | 发现问题时 |
|----|------|-----------|
| **方向** | 我在回答 🔴 已锁定意图吗？ | 回到锁定意图重新开始 |
| **覆盖** | 用户的子问题全覆了吗？ | 下一轮处理遗漏的 |
| **编造** | 这句有知识库依据吗？ | 没依据 → 标注「根据通用知识」 |

Code Review 专用三关：判断有依据吗（每 🔴 必须指向具体代码行）→ 漏了什么（文件/维度全覆盖）→ 在凑数吗（"可以更好"≠"真的错了"）。

外部 Checkpoint + Reflector 保留作为兜底 — 语义对齐静态检查 + 质量评分。

---

## 4 个 Skill

| Skill | 工具数 | 能力 | 输出格式 |
|-------|:---:|------|---------|
| **prompt_refiner** | 2 | 大白话 → 追问 → 2-3 优化版提示词（策略/推荐模型/风格/理由） | 结构化 Markdown |
| **work_arranger** | 4 | 模糊想法 → 追问 → 阶段/任务/时间线/工具推荐/风险/MVP | 含表格的结构化方案 |
| **info_retention** | 3 | 对话/文件 → 追问 → 结构化留存文档 → 落盘 | Markdown 文档 |
| **code_review** | 3 | 读代码 → 知识库查最佳实践 → 按严重程度排序的审查报告 | 🔴🟡🟢 三级分类报告 |

每个 Skill 只暴露它真正需要的工具子集（2-4 个），减少模型选择负担。

---

## 多 Provider LLM

`core/llm_client.py` — 装饰器注册模式 `@_reg("provider_name")`，加 provider 只需一个函数。auto 模式按优先级扫描环境变量自动选择。所有 LLM 调用点（Router/Planner/Executor/Checkpoint/Reflector/ContextEngine L2/L3/SessionMemory/UserProfile）共用同一模型实例，温度=0.7，超时=120s。

**单次对话成本**（deepseek-chat）：≈ ¥0.01。一天 100 次 ≈ ¥1。用 qwen-turbo ≈ ¥0.30/天。

---

## 监控与运维

| 维度 | 实现 |
|------|------|
| **Token 追踪** | SSE done 事件含 `tokens_used` + `input_tokens_est`。日志 `[Agent] start` + `[Agent] done` 带双端 token 计数 |
| **日志** | RotatingFileHandler, 5MB×4, UTF-8。每模块独立 logger 前缀标识 |
| **反馈** | POST /api/feedback (👍👎) + GET /api/feedback/stats。PostgreSQL feedback 表 |
| **健康检查** | GET /api/health → `{"status": "ok", "provider": "deepseek"}` |
| **部署** | Docker Compose + nginx 反代 + Let's Encrypt SSL。`scripts/deploy.sh` 首次部署 + `scripts/update.sh` 智能增量更新（自动检测代码变更，只重建变化的子项目） |

---

## 核心设计决策

| 决策 | 选择 | 理由 |
|------|------|------|
| Agent 范式 | **ReAct (Think→Act→Observe)** | 所有决策点 LLM 推理，可追踪 |
| 工具数量 | **5 个，零重叠** | 从 12 个砍掉 7 个冗余/规则引擎工具。每个标注 "什么时候用 / 坚决不用 / 与其他 tool 关系" |
| 联网搜索 | **不做** | RAG + 模型自身知识覆盖个人工作流场景 |
| 记忆系统 | **三层架构 (L1+L2+L3)** | 时间×粒度矩阵：近期完整 + 全量压缩 + 原子可检索 |
| 反思机制 | **内化为主 + 外部兜底** | 0 额外 LLM 调用 + Checkpoint/Reflector 兜底 |
| 数据库 | **PostgreSQL 统一** | SQLite 已被完全移除。sessions + messages + feedback + domain_knowledge + session_memory + user_profile 全部在同一个 PG 实例 |
| 追问策略 | **少轮多问 + 精简文案** | 3→5 题/轮，删除所有解释性废话 |
| 多 Agent | **暂不做** | 95% 对话单 Skill 可覆盖。为未来 LangGraph Send API 预留基础 |

---

## 未来路线图

### 短期（下个迭代）

- **P0** 前端统一对话入口（替代三卡片落地页）— 降低用户认知门槛
- **P0** code_review 接入 python_exec — 读代码后跑一下验证逻辑
- **P1** LangSmith / LangFuse 全链路 Tracing — 替代 grep 日志排查
- **P1** pgvector HNSW 索引升级 — 当前 IVFFlat 在大数据量下召回率下降

### 中期

- **并行子任务** — Planner 检测到多个独立 subtask 时，LangGraph Send API 并行 spawn 多个 Skill Agent，Synthesizer 合并结果
- **跨 Skill 合成** — 一趟对话完成 "审查代码 + 整理文档" 这种复合需求
- **知识库自进化** — 对话中提炼的知识自动提案给用户确认后写入，而不是等用户主动说 "存一下"
- **Human-in-the-Loop** — python_exec / run_shell_preview 执行前可配置确认门控

### 长期探索

- **本地模型优先** — 敏感场景（代码审查涉及未发布代码时）自动切本地模型
- **Skill 市场** — 用户自定义 Skill YAML → 热加载，无需重启
- **语音入口** — Whisper STT + TTS，开车/散步时能用

---

## 项目统计

| 维度 | 数据 |
|------|------|
| 代码行数 | ~8,000 行 Python + ~1,000 行 JS/CSS/HTML |
| 文件数 | ~60 源文件 |
| 测试 | 21 unit tests (graph + session)，全部通过 |
| 文档 | 10 篇技术文档 (docs/) + CLAUDE.md + GOVERNANCE.md + boundary.md |
| 工具 | 5 个（从 12 个精简） |
| Skill | 4 个 |
| LangGraph 节点 | 8 个 |
| LLM Provider | 4 个 (DashScope / DeepSeek / OpenAI / Local) |
| PGVector Collection | 3 个 (domain_knowledge / session_memory / user_profile) |
| PostgreSQL 业务表 | 3 个 (sessions / messages / feedback) |
| Git commits | 40+ |

---

## 个人贡献亮点

1. **从 12 tools 砍到 5 个** — 每个精简都有明确的理由文档。不是堆功能，是砍冗余。工具之间零重叠，每段 docstring 标注三要素。

2. **三层记忆系统设计** — L1 原始窗口 + L2 滚动摘要（增量更新公式，O(1) 成本）+ L3 语义事实（LLM 提取 6 种分类 + PGVector 语义检索 + 内存后备）。带主题切换检测和自动重置。

3. **反思内化** — 把外部 Checkpoint + Reflector 的自查逻辑内化到 System Prompt，零额外 LLM 调用。代码审查专用三关。

4. **🔴 已锁定意图 + 工作记忆** — 解决多轮对话中意图偏移和信息遗忘的两个系统性修复。在 prompt 结构层面做文章，不改模型不改框架。

5. **RAG 生产级管道** — SemanticChunker 语义分块 + Dense+BM25 混合检索 + RRF 融合 + qwen3-rerank Cross-Encoder 精排 + 关键词加权 + 相似度过滤。content_hash 去重，零冗余 embedding 调用。

6. **SQLite → PostgreSQL 统一** — 删除 SQLite 和 WSL workaround，sessions/messages/feedback + domain_knowledge/session_memory/user_profile 全部 PG。

7. **文档体系** — 10 篇深度技术文档（RAG 深挖 / 三层 RAG 架构 / 幻觉防御 / 工具防循环 / Context Engineering / Token 监管 / Badcase 复盘 / 日志管理 / 三层 Memory 设计 / 意图识别修复），每篇都是工程实践记录不是自动生成。
