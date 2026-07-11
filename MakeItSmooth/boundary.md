# Boundary — MakeItSmooth 约束与质量规范

> Harness Engineering 落地文件。定义 Agent 行为的边界、质量标准、和设计要求。
> 进度追踪与待办事项见 [TODO.md](TODO.md)。

---

## 当前架构 (V3)

```
                         用户消息
                            │
                    agent.py : _build_initial_state()
                            │
                    ┌───────┼───────┐
                    ▼       ▼       ▼
            ContextEngine.build()
            ├─ L1: 最近 3 轮原文     (零成本, 直接注入)
            ├─ L2: 滚动摘要         (LLM 增量更新, 覆盖全历史)
            └─ L3: 语义事实召回      (规则提取 + 关键词匹配)
                    │
                    ▼
            LangGraph 图执行
            ┌───────────────────────────────────────────┐
            │ START → router → enrich → rag → planner   │
            │                                    │       │
            │                          ┌─ clarify → END │
            │                          └─ execute       │
            │                               │           │
            │                          checkpoint ← Planner 语义中枢
            │                           │       │        │
            │                     reflect ← execute      │
            │                        │                   │
            │                   retry execute → END      │
            └───────────────────────────────────────────┘
                    │
                    ▼
            agent.py : update_after_turn()
            ├─ L2: 增量更新摘要
            └─ L3: 提取原子事实
```

---

## 1. 工具边界 — 无重叠、调用精准、防循环

### 1.1 工具清单

| 工具 | 类别 | 用途 | **不要用** |
|------|------|------|-----------|
| `search_knowledge_base` | 信息检索 | 查本地知识库 (PGVector) | 需要实时信息时、本地明显没有答案时 |
| `search_web` | 信息检索 | 联网搜索最新信息 | 本地 KB 已有答案时、纯代码问题、常识性问题 |
| `fetch_url` | 信息检索 | 抓取指定网页内容 | 需登录的页面、大文件下载、API 接口 |
| `python_exec` | 代码执行 | 数据分析、计算验证、格式转换 | 纯文本处理、简单计算、不需要代码就能回答的问题 |
| `add_to_knowledge_base` | 知识管理 | 持久化有价值的对话信息 | 临时信息、闲聊内容、重复内容、用户隐私 |
| `run_shell_preview` | 系统感知 | 只读查看项目结构/文件/Git | 需要写入/修改时、不确定命令是否安全时 |
| `delegate_task` | Multi-Agent | 复杂子任务需要独立调研时 | 简单搜索、只需查一个网站、已有明确答案时，禁止重复 delegate |
| `parse_text` | 文本处理 | 结构化数据提取 (JSON/表格/日志) | LLM 自己能做的简单提取、语义理解型提取 |
| `compare_texts` | 文本处理 | 行级文本差异对比 + 相似度统计 | 语义对比（交给 LLM）、单段文本 |
| `summarize_text` | 文本处理 | 规则引擎文本压缩 (非 LLM) | 需要语义理解的摘要（让 LLM 直接总结） |

### 1.2 调用优先级

```
search_knowledge_base(P0) → search_web(P1) → fetch_url(P2) → delegate_task(P4 兜底)
```

### 1.3 防循环规则

详见 [docs/tool-loop-prevention.md](docs/tool-loop-prevention.md) — 三层防线 (Prompt约束 / 硬计数器 / 模式检测)。

- `delegate_task` 同一个子任务 key 不允许重复调用超过 1 次
- 任何工具连续 3 轮被调用且返回相似结果 → 终止该工具链
- 工具调用超过 8 轮未进入最终输出阶段 → 强制停止，返回当前最佳结果

### 1.4 边界要求

- `add_to_knowledge_base` 和 RAG `ingest_knowledge_base` 写入路径统一入口
- 工具调用防循环 tracking 系统
- `delegate_task` 加 usage_count 追踪

---

## 2. Context Engineering — 三层上下文管理

### 2.1 架构

```
L1 原始窗口    最近 3 轮完整原文           零 LLM 调用  直接注入 prompt
L2 滚动摘要    全部历史的压缩版             每轮 LLM 1 次  直接注入 prompt
L3 语义事实    LLM 结构化提取 + PGVector 语义召回  每轮 LLM 1 次  按需注入 prompt
```

### 2.2 各层详解

| | L1 滑动窗口 | L2 滚动摘要 | L3 语义事实 |
|---|---|---|---|
| 存什么 | 最近 3 轮 user+assistant 原文 | 全历史压缩为 ~256 token 摘要 | LLM 精准提取的原子事实（偏好、决策、约束） |
| 存储位置 | 不存储（每次从 SQLite 读） | ContextEngine._running_summary (内存) | PGVector session_memory 表 + 内存字典后备 |
| 更新时机 | 每轮重新读取 | 每轮对话后增量合并 | 每轮对话后 LLM 提取 → embedding → PGVector |
| 注入方式 | 🟡 最近对话 | 🔴 前情提要 (最高优先级) | 🟢 语义事实 (PGVector 语义召回, 跨会话可用) |

### 2.3 设计原则

- L2 增量更新: 旧摘要 + 本轮新内容 → 新摘要，不重建全部历史
- L3 规则提取: 匹配 "我用/我喜欢/不要/必须/决定" 等模式 + 技术栈声明 + 时间/资源约束
- L3 存储: 当前内存字典，会话级 TTL=20 轮
- 主题切换时 L2 摘要应重置

### 2.4 注入位置

```
Planner prompt:  🔴L2摘要 + 🟡L1原文 + 🟢L3事实 + RAG + 用户消息
Executor prompt: 同 Planner + ⚠️checkpoint 反馈
Reflector prompt: RAG上下文 + 用户原始需求 + 实际输出
Checkpoint prompt: Planner 目标 + L2/L1 上下文 + RAG + 用户消息 + Executor 输出
```

### 2.5 边界要求

- [x] L3 从规则提取 → LLM 提取 — **已完成**
- [x] L3 从内存字典 → PGVector 持久化 — **已完成**
- [x] 主题切换检测 — **已完成** (keyword 重叠率快检 → L2/L3 自动重置)
- 压缩质量评估体系

---

## 3. 测试体系 — Badcase 规范

### 3.1 Badcase 来源

| 来源 | 触发条件 | 存储格式 |
|------|---------|---------|
| Reflector 评分 | score < 5 | 自动保存 input + output + score + issues |
| Checkpoint 偏移 | aligned = false | 自动保存 input + output + drift_description |
| 用户点 👎 | 前端反馈按钮 | 自动保存 input + output |
| 工具调用异常 | > 8 轮未结束 / 工具报错 | 自动保存 input + tool trace |
| Router 误分类 | confidence < 0.5 | 自动保存 input + predicted + expected |
| 手动收集 | 开发者发现 | 手工写入 JSONL |

### 3.2 Badcase 存储格式

```jsonl
{"id":"bc_001","input":"帮我写个提示词","expected_module":"prompt_refiner","actual_module":"work_arranger","type":"router_misclassify","severity":"high"}
{"id":"bc_002","input":"React 18 Suspense 怎么用","expected_output_contains":"Suspense","actual_output":"（讲了一堆 Vue 的东西）","type":"rag_hallucination","severity":"high"}
{"id":"bc_003","input":"用 React 写博客","output_contains":"推荐 Redux","type":"l3_fact_miss","severity":"medium","note":"L3 有事实'用户不要 Redux'但未召回"}
```

### 3.3 边界要求

- 所有 badcase 存入 `tests/badcase_regression.jsonl`
- Reflector score < 5 自动保存
- Checkpoint aligned=false 自动保存
- 用户 👎 → 自动记录
- 补充集成测试（完整图运行一条消息）
- 补充 E2E 测试（SSE streaming token 级别验证）
- L3 语义事实召回率测试

---

## 4. RAG — 混合检索与幻觉防御

### 4.1 检索架构

```
用户 query
    │
    ├─ Dense 检索 (PGVector)  → top-20    语义模糊匹配
    ├─ BM25 检索 (PG tsvector) → top-20    术语精确命中
    └─ 知识图谱摘要 (待实现)    → 结构化大纲  source_file 聚合
         │
         ▼
    RRF 合并去重 → top-20
         │
         ▼
    qwen3-rerank 精排 → top-5
         │
         ▼
    相似度过滤 (≥0.6) → top-3
         │
         ▼
    注入 Prompt（带来源引用 + 知识边界声明）
```

### 4.2 幻觉防御层

| 防御 | 机制 | 阈值 |
|------|------|------|
| 相似度过滤 | chunk similarity | < 0.6 不注入，标记 "未找到相关知识" |
| 关键词重叠检查 | query 核心名词 ∩ 检索结果词频 | 重叠率 < 30% → 警告标记 |
| 来源强制引用 | 每个 chunk 注明 source_file + 更新时间 | 模型被要求在输出中引用来源 |
| Checkpoint 事实核查 | "输出中的技术细节是否在知识库参考中？" | 找不到 → 标记语义偏移 |
| 低相似度降级 | 所有 chunk similarity < 0.5 | 不注入 RAG，直接告诉用户 "知识库未覆盖" |

### 4.3 RAG 实现状态

| 技术 | 状态 |
|------|------|
| 语义分块 (SemanticChunker) | ✅ |
| Dense 检索 (PGVector cosine) | ✅ |
| BM25 全文检索 (PG tsvector + GIN) | ✅ |
| RRF 混合合并 | ✅ |
| qwen3-rerank 精排 | ✅ |
| 相似度阈值过滤 | ✅ |
| 关键词重叠加权 | ✅ |
| 来源强制引用 (Prompt 层) | ✅ |
| Checkpoint/Reflector RAG 注入 | ✅ |
| 上下文驱动 Query 增强 | ✅ |
| Embedding: text-embedding-v4 | ✅ |
| 知识图谱摘要 (L3 RAG) | ⬜ |
| Self-query 元数据过滤 | ⬜ |
| Parent Document Retriever | ⬜ |
| Query Decomposition | ⬜ |

### 4.4 边界要求

- Query 增强原则: 只组合真实信息，不生成虚假信息（不使用 HyDE）
- 短 query: 从对话上下文 (L3+L2+dims) 组合，上下文不够 → clarify 反问
- 长 query (>80字符): 不增强，保护原始语义
- BM25 使用 PG `simple` 分词器（避免英文词干化对中文的副作用）
- Rerank: 百炼 qwen3-rerank（120K token / 500 docs / 100+ 语言）

---

## 5. 注意力管理与 Agent 架构

### 5.1 Agent 节点分工 (V3)

```
Router      意图分类       轻量 LLM + 规则 fallback         单模块入口
Planner     语义分析       维度提取 + 完整度判断 + 执行计划    JSON mode, 单次
Clarify     追问生成       规则模板兜底                      非 LLM
Execute     ReAct 执行     tool calling loop                 最多 10 轮
Checkpoint  语义枢纽       Planner 持续介入检查方向           JSON mode, 单次 (新增)
Reflect     质量审查       完整性 + 准确性 + 幻觉检测 + 重试建议  JSON mode, 单次
```

### 5.2 🔴🟡🟢⚪ 注意力层级

```
🔴 L2 滚动摘要 — 最高优先级，放 prompt 最前面，模型必须了解
🟡 L1 最近原文 — 当前对话的准确上下文
🟢 L3 语义事实 / RAG / 对话历史 — 参考用，按需阅读
⚪ 原始上下文 — 用户原始消息 + 已确认维度，仅用于理解意图
⚠️ Checkpoint 反馈 — 只在有语义偏移时注入，覆盖 🟡 层级
```

### 5.3 设计原则

1. **层级标记** — 🔴🟡🟢⚪ 视觉分隔，模型训练数据中天然对标记符号有注意力偏差
2. **指令在前，参考在后** — 越靠前注意力越高
3. **每段 ≤ 5 条** — 超过折叠为摘要
4. **对称结构** — 每段格式一致，减少解析负担
5. **不使用否定指令** — 不说 "不要忽略"，说 "必须考虑"
6. **字符预算** — L2 ≤ 500 字符, L1 ≤ 1500 字符, L3 ≤ 500 字符
7. **Token 预算** — prompt 组装后总 token 超 6K → 压缩 L1 为 1 轮

### 5.4 边界要求

- Checkpoint 独立重试计数（不依赖 reflection_count）
- Checkpoint 最多重试 1 次后必须进入 Reflector
- Reflector 必须包含 hallucination 检测维度
- Reflector 也使用 🔴🟡🟢⚪ 层级标记

---

## 6. 工具标注规范 — Docstring 三段式

### 6.1 要求格式

每个 `@tool` 的 docstring 必须包含：

```python
@tool
def tool_name(param: str) -> str:
    """
    【用途】一句话说清楚这个工具干什么。
    【不要用】明确列出不能使用的场景（至少 3 条）。
    【优先级】🔴🟡🟢 + 调用顺序。
    【参数/返回】参数要求 + 返回格式说明。
    【限制/前置条件】如需要 API key、超时、安全风险等。
    """
```

### 6.2 状态

全部 12 个工具已完成三段式标注 + ALL_TOOLS 注册。

---

## 附录：检查清单

每次代码变更时自查：

- [ ] 新加的 tool 有三段式 docstring？（§6）
- [ ] Planner + Executor + Checkpoint prompt 包含三层上下文？（§2）
- [ ] RAG 检索结果有相似度过滤？（§4）
- [ ] Prompt 使用了 🔴🟡🟢⚪ 层级标记？（§5）
- [ ] 有没有新增 badcase 需要记录？（§3）
- [ ] 工具调用是否有循环风险？（§1）
- [ ] L3 是否提取了本轮的原子事实？（§2）
- [ ] Checkpoint 是否能拦截语义偏移？（§5）
- [ ] Query 增强是否只组合了真实信息？（§4 原则）
