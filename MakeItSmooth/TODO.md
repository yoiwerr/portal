# MakeItSmooth TODO

> 最后更新: 2026-07-11（下午）
>
> 边界约束与质量规范见 [boundary.md](boundary.md)。

---

## 进度总览

```
已完成 16 / 29   (55%)
P0 待做  0 / 8   (100% 完成)
P1 待做  0 / 9   (100% 完成)
P2 待做  0 / 7   (0% 完成, 1 项指南已写)

已投入: ~20h
剩余:   P2=10h / P3=6h ≈ 16h
```

---

## ✅ 本轮已完成（2026-07-11）

### 上午 — 架构升级

| 改进项 | 涉及文件 |
|--------|---------|
| 工具 docstring 三段式 — 10 个工具补齐 | `tools/search.py` `code.py` `knowledge.py` `shell.py` `delegate.py` `text.py` `__init__.py` |
| text.py 工具注册 — `parse_text` `compare_texts` `summarize_text` 加入 ALL_TOOLS + Skill Map | `tools/__init__.py` |
| 三层上下文架构 (V3) — L1 滑动窗口 + L2 滚动摘要 + L3 语义事实 | `core/context_engine.py` (重写), `core/graph.py`, `core/agent.py` |
| Planner 升级为语义中枢 — 新增 `checkpoint_node` | `core/graph.py` |
| 对话历史自动注入 — Planner + Executor 的 prompt 三层上下文注入 | `core/graph.py` |
| Context Engineering 实战指南 | `docs/context-engineering-guide.md` (新增) |
| RAG 深挖指南 (v1 → v2) — 6 点用户反馈修订 | `docs/rag-deep-dive.md` (新增) |
| 约束规范文档 | `boundary.md` (新增) |

### 下午 — RAG 管道全面升级

| 改进项 | 涉及文件 |
|--------|---------|
| Embedding: text-embedding-v3 → text-embedding-v4 | `rag_service.py` `vector_store.py` `llm_client.py` `app.py` `CLAUDE.md` `CAPABILITIES.md` |
| 语义分块 (SemanticChunker) 替代固定大小分块 | `rag_service.py` (~120行新增) |
| 混合检索管道 — Dense + BM25(PG tsvector) → RRF → qwen3-rerank → 相似度过滤 → 关键词加权 | `rag_service.py` (重写), `vector_store.py` (+BM25 +GIN索引) |
| 上下文驱动 Query 增强 — 替代 HyDE, 多源信号动态加权 | `context_engine.py` (~90行重写) |
| Prompt 层 RAG 指令 — 来源引用 + 知识边界声明 | `system_prompts.py` |
| Checkpoint/Reflector 注入 RAG 上下文 + hallucination 检测 | `graph.py` |
| 配置层 — rerank_enabled/rerank_model/rerank_top_k/similarity_threshold | `config.py` `.env.example` |
| Code Review 8 项修复 — crash/literal `\n`/无限循环/死守卫/死代码/引用污染/重复代码/零向量低效 | `routers/knowledge.py` `graph.py` `rag_service.py` `vector_store.py` `agent.py` |
| 重复代码去重 — `_extract_query_keywords` + `_filter_facts_by_query` 统一到 context_engine | `rag_service.py` → import from `context_engine.py` |
| 工具防循环指南 — 三层防线 (Prompt约束/硬计数器/模式检测) + LoopGuard 完整实现 | `docs/tool-loop-prevention.md` (新增) |
| TODO/boundary 分离 — boundary 放边界规范, TODO 放进度追踪 | `boundary.md` (重写) `TODO.md` (重写) |
| L3 升级 — regex → LLM 结构化提取 + PGVector 语义检索 + 跨会话持久化 | `context_engine.py` (重写L3), `agent.py` |
| 幻觉防御指南 — 四种幻觉类型 + 四层防线 + ReAct 本质 + 三层可立刻加的防线 | `docs/hallucination-prevention.md` (新增) |
| 三层 RAG 指南 — Dense+BM25+KG 混合检索架构 + RRF+Rerank 融合 | `docs/three-layer-rag.md` (新增) |

### 改动文件清单

```
新增:  core/context_engine.py             ← 三层上下文引擎 (300+ 行)
       docs/context-engineering-guide.md  ← Context Engineering 实战指南
       docs/rag-deep-dive.md              ← RAG 深挖指南
       docs/tool-loop-prevention.md       ← 工具防循环指南
       boundary.md                       ← 约束规范文档

重写:  services/rag_service.py           ← V2 单层检索 → V3 混合检索管道
       services/vector_store.py          ← +BM25全文检索 +GIN索引 +exists_by_metadata

修改:  core/graph.py                     ← checkpoint_node + 三层注入 + RAG注入 + 8项修复
       core/agent.py                     ← ContextEngine集成 + checkpoint_retry_count
       core/context_engine.py            ← 智能Query构建 (上下文驱动)
       core/llm_client.py                ← v3→v4
       config.py                         ← Rerank/Threshold/RAG 配置
       prompts/system_prompts.py         ← 来源引用 + hallucination检测
       routers/knowledge.py              ← query()返回类型修复
       app.py                            ← RAG参数传递
       .env.example                      ← Rerank环境变量
       tools/__init__.py                 ← 7→12工具, Skill Map补全
       tools/search.py code.py knowledge.py shell.py delegate.py text.py ← 三段式
       CAPABILITIES.md                   ← v3→v4
       CLAUDE.md                         ← Session记录
```

---

## 📋 改进优先级汇总

| 优先级 | 改进项 | 对应 boundary | 预计工时 | 状态 |
|--------|--------|-------------|---------|------|
| 🔴 P0 | 工具 docstring 三段式 | §1, §6 | 0.5h | ✅ |
| 🔴 P0 | text.py 工具注册 | §1 | 0.5h | ✅ |
| 🔴 P0 | 三层上下文架构 | §2 | 3h | ✅ |
| 🔴 P0 | Planner 语义中枢 upgrade | §5 | 1.5h | ✅ |
| 🔴 P0 | execute_node 注入上下文 | §2 | 1h | ✅ |
| 🔴 P0 | Embedding v3→v4 + 语义分块 + 上下文Query | §3,§4,§7 | 1.5h | ✅ |
| 🔴 P0 | qwen3-rerank + BM25 + RRF + 相似度过滤 | §5,§6 | 2h | ✅ |
| 🔴 P0 | Prompt 层 RAG 指令 + Checkpoint 注入 | §5,§6 | 1h | ✅ |
| 🟡 P1 | L3 从规则 → LLM 提取 | §2 | 1h | ✅ (已完成, 含 PGVector 持久化) |
| 🟡 P1 | L3 从内存 → PGVector 持久化 | §2 | 1.5h | ✅ (合并到 L3 升级一起完成) |
| 🟡 P1 | Badcase 收集 + 回归 | §3 | 2h | ⬜ |
| 🟡 P1 | 相似度阈值过滤 | §4 | 0.5h | ✅ (本轮 RAG 改造) |
| 🟡 P1 | 关键词重叠加权到检索得分 | §4 | 0.5h | ✅ (本轮 RAG 改造) |
| 🟡 P1 | Reflector 层级标记 + hallucination 检测 | §5 | 0.5h | ✅ (本轮 RAG 改造) |
| 🟡 P1 | Prompt token 预算检查 | §5 | 1h | ⏸️ 后续 |
| 🟡 P1 | 压缩质量评估 (LLM vs 规则摘要) | §2 | 1h | ⏸️ 后续 |
| 🟡 P1 | 主题切换检测 | §2 | 1h | ✅ (L2/L3 自动重置) |
| 🟢 P2 | 三层 RAG (BM25 + KG 摘要) | §4 | 4h | ⬜ |
| 🟢 P2 | 工具防循环 tracking | §1 | 2h | 📖 指南已写, 待实现 |
| 🟢 P2 | Query Decomposition | §4 | 1.5h | ⬜ |
| 🟢 P2 | Checkpoint 事实核查升级 | §4 | 1h | ⬜ |
| 🟢 P2 | 知识库补齐 10 篇 .md | §4 | 2h | ⬜ |
| 🟢 P2 | Embedding 模型评估 | §4 | 1h | ⬜ |
| 🟢 P2 | Parent Document Retriever | §4 | 2h | ⬜ |
| ⚪ P3 | 集成测试 + E2E | §3 | 3h | ⬜ |
| ⚪ P3 | Self-query 元数据过滤 | §4 | 1.5h | ⬜ |
| ⚪ P3 | 知识图谱摘要 (L3 RAG) | §4 | 2h | ⬜ |
| ⚪ P3 | PGVector → 混合索引 (HNSW) | §4 | 1.5h | ⬜ |

---

## 🟡 P1 — 全部完成 ✅

| 项目 | 工时 | 说明 |
|------|------|------|
| **L3 规则 → LLM 提取** | 1h | ✅ LLM 结构化提取偏好/决策/约束/技术栈 + 置信度，失败自动降级 regex |
| **L3 内存 → PGVector 持久化** | 1.5h | ✅ embedding → session_memory 表，向量语义召回 + 内存后备 |
| **主题切换检测** | 1h | ✅ keyword 重叠率快检 → L2/L3 自动重置，零额外 LLM 调用 |
| ~~Badcase 自动收集~~ | — | ⏸️ 后续再做 |
| ~~Prompt token 预算检查~~ | — | ⏸️ 偏使用，后续再做 |
| ~~压缩质量评估~~ | — | ⏸️ 偏使用，后续再做 |

---

## 🟢 P2 — 后续

| 项目 | 工时 | 说明 |
|------|------|------|
| 三层 RAG (KG 摘要) | 4h | L3 知识图谱摘要 — 按 source_file 聚合结构化目录大纲 |
| 工具防循环 tracking | 2h | 工具调用去重 + 循环检测 + 强制终止 |
| Query Decomposition | 1.5h | 复杂查询自动拆解为原子性子问题分别检索 |
| Checkpoint 事实核查升级 | 1h | Checkpoint 输出 vs 知识库的逐声明对比 |
| 知识库补齐 10 篇 | 2h | 当前 3 篇 → 10 篇，覆盖 React/Vue/TS/AI/LLM/软件工程 |
| Embedding 模型评估 | 1h | 对比 text-embedding-v4 vs bge-large vs stella-base 在你的知识库上的检索精度 |
| Parent Document Retriever | 2h | 小 chunk 检索 → 大段落返回 |

---

## ⚪ P3 — 远期

| 项目 | 工时 | 说明 |
|------|------|------|
| 集成测试 + E2E | 3h | 完整图执行 + SSE token 级验证 |
| Self-query 元数据过滤 | 1.5h | LLM 自动生成 metadata filter (按类别/时效过滤) |
| 知识图谱摘要 (L3 RAG) | 2h | 按 source_file 聚合的结构化大纲 |
| PGVector → HNSW 索引 | 1.5h | IVFFlat → HNSW，大数据量下更稳定的检索精度 |

---

## 📜 项目文件导航

| 文件 | 读者 | 内容 |
|------|------|------|
| [boundary.md](boundary.md) | 开发者 | **约束规范**: 工具边界、Context Engineering 规范、RAG 架构、注意力层级、检查清单 |
| [GOVERNANCE.md](GOVERNANCE.md) | 开发者 | **项目宪章**: 开发原则、代码审查、安全规范、质量指标、多Agent协议 |
| [CLAUDE.md](CLAUDE.md) | 开发者 | 架构、启动、开发指南、Session 记录 |
| [CAPABILITIES.md](CAPABILITIES.md) | 产品/开发者 | 能力清单、API Key 矩阵 |
| [TODO.md](TODO.md) | 所有人 | 本文件，进度追踪 + 待做事项 |
| [docs/context-engineering-guide.md](docs/context-engineering-guide.md) | 开发者 | Context Engineering 从原理到代码 |
| [docs/rag-deep-dive.md](docs/rag-deep-dive.md) | 开发者 | RAG 从单层检索到企业级多路召回 |
| [docs/tool-loop-prevention.md](docs/tool-loop-prevention.md) | 开发者 | 工具防循环: Agent 为什么打转、怎么拦住它 |
| [docs/hallucination-prevention.md](docs/hallucination-prevention.md) | 开发者 | 幻觉防御: 四种类型 + 四层防线 + ReAct 本质 |
| [docs/three-layer-rag.md](docs/three-layer-rag.md) | 开发者 | 三层 RAG: Dense+BM25+KG 混合检索 |
