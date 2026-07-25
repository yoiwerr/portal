# 三层 Memory 设计

> 对话记忆不只是"记住刚才说了什么"——是时间维度 × 粒度维度的工程矩阵

## 1. 为什么需要三层

单层记忆不够用，因为两种需求互相矛盾：

| 需求 | 要什么 | 如果只用一层 |
|------|--------|-------------|
| 当前对话流畅 | 最近的完整原文，一字不差 | 压缩摘要会丢失细节 |
| 长对话不丢上下文 | 全部历史的压缩版 | 原文窗口塞不下 |
| 精准回忆偏好 | 用户说过的具体事实，可检索 | 摘要太粗，检索不到 |

三层是这三个矛盾解的工程组合：

```
       ┌──────────────┬──────────────────┬─────────────┐
       │    时间维度    │     粒度维度      │   成本维度   │
       ├──────────────┼──────────────────┼─────────────┤
  L1   │ 最近 3 轮     │ 完整原文          │ 零 LLM 调用  │
  L2   │ 全部历史      │ 滚动压缩摘要       │ 每轮 1 次    │
  L3   │ 全部历史      │ 原子事实 (可检索)  │ 每轮 1 次    │
       └──────────────┴──────────────────┴─────────────┘
```

---

## 2. 全景架构

```
                          ┌─────────────────────────┐
                          │      Agent (每轮对话)     │
                          └──────────┬──────────────┘
                                     │
              ┌──────────────────────┼──────────────────────┐
              │ 对话前                                   对话后 │
              ▼                                              ▼
    ┌─────────────────┐                        ┌─────────────────┐
    │ ContextEngine   │                        │ ContextEngine   │
    │   .build()      │                        │ .update_after   │
    │                 │                        │   _turn()       │
    │ L1 ← messages   │                        │                 │
    │ L2 ← _running   │                        │ L2 旧摘要+本轮   │
    │      _summary   │                        │   → 新摘要 (LLM) │
    │ L3 ← PGVector   │                        │                 │
    │  + 内存后备      │                        │ L3 提取事实 (LLM) │
    │                 │                        │   → PGVector    │
    │ 注入到 prompt   │                        │   → 内存后备     │
    └─────────────────┘                        └─────────────────┘

             会话完成时 (一次性)

    ┌─────────────────┐        ┌─────────────────┐
    │ SessionMemory   │        │  UserProfile    │
    │                 │        │                 │
    │ 全量对话 → LLM  │        │ 消费 L2 摘要 →  │
    │ 结构化摘要 JSON  │        │ 更新技术栈/偏好  │
    │ → PGVector      │        │ /项目/领域      │
    │                 │        │ → PGVector      │
    │ 跨会话检索用     │        │ (单文档)        │
    └─────────────────┘        └─────────────────┘
```

---

## 3. 第三层 — ContextEngine (单会话内)

位置: `core/context_engine.py`

### 3.1 L1 — 原始窗口

**一句话**: 最近 3 轮的完整 user→assistant 原文，一字不改。

```
轮次 1-4 的对话 (8 轮历史):
  ...
  轮 5 ← 丢弃
  轮 6 ← 丢弃
  轮 7 ← L1 保留 (第 1/3 轮)
  轮 8 ← L1 保留 (第 2/3 轮)
  轮 9 ← L1 保留 (第 3/3 轮) ← 当前轮次
```

- **提取方式**: 从 PostgreSQL `messages` 表直接读，配对 user→assistant
- **注入方式**: 拼到 Executor 的 System Prompt，标记为 🟡（有 L2 时）或 🟢（无 L2 时）
- **成本**: 零 LLM 调用，纯 SQL 读取
- **变化**: 每轮追加新消息，最老的那轮被挤出窗口
- **上限**: `L1_MAX_TURNS = 3`（约 2000 tokens）

### 3.2 L2 — 滚动摘要

**一句话**: 全部对话历史的压缩版，每轮增量更新。

**增量更新公式**:
```
新 L2 = LLM(旧 L2 + 本轮对话内容)
```

不是每轮把全量历史扔给 LLM 重新摘要。而是 `旧摘要 + 本轮新内容 → 新摘要`。O(1) 的 LLM 成本，无论历史多长。

- **内容格式**: `用户想要...。已确定: ...。上次: ...`（第三人称）
- **保留**: 核心需求、已做决策、关键约束、重要偏好
- **丢弃**: 追问细节、问候语、过渡语句、工具调用的中间结果
- **上限**: `DEFAULT_MAX_SUMMARY_TOKENS = 256`（约 750 中文字）
- **注入方式**: 拼到 Planner/Executor 的 System Prompt，标记为 🔴（最高优先级）
- **降级**: LLM 调用失败 → 保持旧摘要不变

**主题切换检测**:
```
用户说 "帮我审查代码" → 之前聊的是 "提示词优化"
                                    ↓
keyword 重叠率 = 0 (代码 vs 提示词，无交集)
                                    ↓
重置 L2 摘要 + 清空 L3 事实 → 以新话题重新开始
```

检测逻辑: 当前消息关键词 vs L2+L3 关键词的重叠率。零重叠 → 直接判定切换（保守策略不会被误判）。

### 3.3 L3 — 语义事实

**一句话**: 从每轮对话中提取原子事实（偏好/决策/约束/技术栈），可跨轮检索。

**提取方式** (双路径):

| 路径 | 触发条件 | 精度 |
|------|---------|------|
| **主路径**: LLM JSON mode 结构化提取 | LLM 可用 | 高 — 6 种分类、置信度标注 |
| **后备**: 正则规则提取 | LLM 不可用 | 中 — 识别"我喜欢/不要/必须/决定"模式 + 技术栈关键词 |

**LLM 提取的 6 种分类**:
```
用户: "我喜欢简洁风格。不要 Redux。必须一个月完成。决定用 Vercel。"

→ LLM 输出 JSON:
{
  "facts": [
    {"text": "用户偏好简洁风格", "category": "偏好", "confidence": 0.9},
    {"text": "用户明确拒绝 Redux", "category": "约束", "confidence": 1.0},
    {"text": "项目截止时间一个月", "category": "约束", "confidence": 1.0},
    {"text": "用户已决定用 Vercel 部署", "category": "决策", "confidence": 1.0}
  ]
}
```

**存储** (双写):
| 路径 | 位置 | 检索方式 |
|------|------|---------|
| **主**: PGVector | `session_memory` 表, type=l3_facts | 向量相似度 (cosine ≥ 0.5) |
| **后备**: 内存字典 | `_fact_store[session_id]` | 关键词匹配 |

**检索方式** (双路径):
```
新消息: "之前说的部署方案是什么？"

1. PGVector 语义检索 (优先):
   query embedding → PGVector session_memory 表
   → cosine ≥ 0.5 → 返回相关事实

2. 内存关键词匹配 (后备):
   "部署" "方案" vs 内存中的事实 → 关键词打分 → 返回 top 5
```

**TTL**: 每会话最多 50 条事实（超出淘汰最旧的）。话题切换时清空。

---

## 4. 第四层 — SessionMemory (跨会话)

位置: `memory/session_memory.py`

**与 ContextEngine L2 的区别**:
| | ContextEngine L2 | SessionMemory |
|----|-----------------|---------------|
| **存什么** | 滚动摘要（非结构化文本） | 结构化 JSON 摘要 |
| **存多久** | 本次会话结束即丢弃（内存） | 持久化到 PGVector，跨会话检索 |
| **什么时候写** | 每轮对话后 | 会话完成时（一次性） |
| **什么时候读** | 每轮对话前（注入 prompt） | 新会话开始时（检索相关历史） |

**写入时机**: 会话完成 (`_summarize_on_complete`)，execute 成功后触发

**写入内容**:
```json
{
  "title": "React 博客搭建工作安排",
  "summary": "用户想用 React + Node.js 搭建个人博客...",
  "decisions": ["确定用 TypeScript", "部署平台选 Vercel"],
  "tech_stack": ["React", "TypeScript", "Node.js", "Vercel"],
  "projects": ["个人博客"],
  "todos": ["配置 CI/CD", "设计数据库 Schema"],
  "tags": ["React", "博客", "TypeScript", "全栈"]
}
```

**检索**: 新会话开始时，用户消息 → embedding → PGVector 向量检索 → top 3 相关历史会话。结果标记为 `🧠 历史相关对话`，拼到 extra_context。

**阈值**: < 3 条消息的对话不摘要（太短没价值）。

---

## 5. 第五层 — UserProfile (长期画像)

位置: `memory/user_profile.py`

**一句话**: 从多次对话中逐渐学习你是谁——技术栈、工作风格、活跃项目、常用工具。

**存储**: PGVector `user_profile` 表，单文档 `id="user_profile_main"`。读取缓存，写入更新。

**更新机制** (双层):

```
SessionMemory 产出摘要 JSON
        │
        ▼
   规则层 (快速合并)
   ├── 新 tech_stack → confidence = 0.5
   ├── 复用 tech_stack → confidence + 0.1 (上限 1.0)
   ├── 新 project → 加到 active_projects
   └── total_conversations + 1
        │
        ▼
   LLM 层 (智能推断)
   ├── 推断 domain (专业领域)
   ├── 推断 work_style (工作风格)
   └── 推断 preferred_tools (常用工具)
        │
        ▼
   合并结果 → 写入 PGVector
```

**画像字段**:
```json
{
  "tech_stack": {"Python": 0.95, "React": 0.8, "TypeScript": 0.6, "PostgreSQL": 0.5},
  "work_style": "偏好简洁实现，先 MVP 再迭代",
  "domain": "全栈 Web 开发 + AI 工具",
  "preferred_tools": ["VSCode", "Docker", "Vercel"],
  "active_projects": ["个人博客", "AI 工作流工具"],
  "total_conversations": 47,
  "updated_at": "2026-07-13T14:30:00"
}
```

**注入方式**: `format_for_context()` → 拼到 extra_context，随 initial_state 注入 Planner 和 Executor。

**置信度机制**: Python=0.95 说明你在 9+ 次对话中反复提到 Python。某技术栈只出现过一次=0.5。置信度低于 0.5 不展示。

---

## 6. 数据流全貌

```
第 1 轮对话
  │
  ├─ 对话前:
  │   L1 = (空, 第一轮)
  │   L2 = (空, 还没有历史)
  │   L3 = (空)
  │   SessionMemory: 无检索 (新会话)
  │   UserProfile: 注入画像 (如果有历史)
  │
  ├─ 对话后:
  │   L2 = "用户想要搭建个人博客。已确定: 用 React+Node.js。"
  │   L3 = ["偏好简洁风格 [偏好]", "已决定用 Vercel [决策]"]
  │   SessionMemory: 不触发 (< 3 条消息)

第 5 轮对话
  │
  ├─ 对话前:
  │   L1 = 第 2/3/4 轮完整对话原文 (最近 3 轮)
  │   L2 = "用户想要搭建个人博客。已确定: React+TS+Node.js+Vercel。上次: 讨论了数据库方案，倾向 PostgreSQL..."
  │   L3 = PGVector 检索到 3 条相关事实: "偏好简洁 [偏好]" "拒绝 Redux [约束]" "决定 Vercel [决策]"
  │
  ├─ 对话后:
  │   L2 = "用户想要搭建个人博客。已确定: React+TS+Node.js+Vercel+PG。上次: 开始写前端组件..."
  │   L3 = 新提取 2 条事实 → PGVector + 内存

会话完成
  │
  ├─ SessionMemory.summarize_and_store()
  │   全量对话 → LLM 摘要 JSON → PGVector session_memory
  │
  └─ UserProfile.update_from_summary()
      规则层: React/TS/Node/PG confidence 各 +0.1
      LLM 层: 推断 domain="全栈 Web 开发"
      → 写入 PGVector user_profile

下次新会话
  │
  ├─ SessionMemory.retrieve("博客 部署")
  │   → 命中上次的博客对话摘要 → 注入 "🧠 历史相关对话"
  │
  └─ UserProfile.format_for_context()
      → "👤 用户画像: React(80%) TypeScript(70%) PostgreSQL(60%) ..."
      → 注入 extra_context
```

---

## 7. 存储全景

| 层 | PGVector Collection | 表/键 | 数据类型 | TTL |
|----|-------------------|-------|---------|-----|
| **L1** | — (不存向量) | PG `messages` 表, session_id 索引 | 原始 user/assistant 文本 | 永久（除非删会话） |
| **L2** | — (不存向量) | ContextEngine `_running_summary` (内存) | 非结构化文本 ~256 tokens | 会话结束丢弃 |
| **L3** | `session_memory` (type=l3_facts) | PGVector + ContextEngine `_fact_store` (内存后备) | 原子事实，带分类和置信度 | 最多 50 条/会话 |
| **SessionMemory** | `session_memory` (type=summary) | PGVector | 结构化 JSON 摘要 | 永久（除非手动清理） |
| **UserProfile** | `user_profile` (id=user_profile_main) | PGVector 单文档 | JSON 画像 | 永久（增量更新） |

**两个系统共用 `session_memory` 表**，通过 metadata.type 区分:
- `type: "l3_facts"` → ContextEngine L3 事实
- `type: "summary"` (或空) → SessionMemory 会话摘要

---

## 8. 成本模型

| 操作 | LLM 调用 | Embedding | 触发频率 |
|------|---------|-----------|---------|
| L1 读取 | 0 | 0 | 每轮 |
| L2 更新 | 1 (~500 in, ~150 out) | 0 | 每轮（首轮跳过） |
| L3 提取 | 1 (~500 in, ~100 out) | 0 | 每轮 |
| L3 写入 PGVector | 0 | 1 (事实文本 → 1024维) | 每轮 |
| L3 检索 PGVector | 0 | 1 (query → 1024维) | 每轮 |
| SessionMemory 写入 | 1 (~2000 in, ~200 out) | 1 (摘要 → 1024维) | 会话完成时 |
| SessionMemory 检索 | 0 | 1 (query → 1024维) | 新会话开始时 |
| UserProfile 更新 | 1 (~1000 in, ~100 out) | 1 (画像 → 1024维) | 会话完成时 |

**每轮对话额外成本** (相比不用记忆系统):
- L2 LLM: +650 tokens
- L3 LLM: +600 tokens
- L3 Embedding: +1 次 API 调用

**用 DeepSeek 计价**: 每轮约 +¥0.002（规则 + LLM + Embedding）。100 次对话/天 = ¥0.20。几乎免费。

---

## 9. 与旧版 (V2) 的差异

| | V2 (旧) | V3 (新) |
|----|---------|---------|
| **L1** | 按轮数阈值切换 (≤2 无 / 3-7 完整 / ≥8 压缩) | 始终保留最近 3 轮 |
| **L2** | 仅在 ≥8 轮时触发一次 LLM 整段压缩 | 每轮增量更新，O(1) 成本 |
| **L3** | regex 提取 → 内存字典 → 关键词匹配 | LLM 提取 → PGVector 向量语义检索 (主) + 内存关键词 (备) |
| **主题切换** | 无检测，旧上下文污染新话题 | keyword 重叠率检测 → 重置 L2 + 清空 L3 |
| **跨会话** | 无 (每次全新) | SessionMemory 摘要检索 + UserProfile 画像注入 |

**V2 的问题**: 比如 7 轮对话后用户突然换了话题，V2 会把全部 7 轮历史完整注入 prompt，上下文被旧话题塞满，新话题的回答质量下降。V3 检测到话题切换后立刻重置。

---

## 10. 常见问题

### Q: L3 的 LLM 提取失败了怎么办？

降级到正则规则提取（识别"我喜欢/不要/必须/决定"模式 + 技术栈关键词列表）。精度下降但不丢失信息。

### Q: PGVector 不可用了怎么办？

L3 读写回到内存字典（`_fact_store`）。SessionMemory 和 UserProfile 的写入跳过（下次启动会丢失），但不会阻塞对话。

### Q: L2 摘要会不会累积错误？

有可能。旧摘要有一个错误（"用户想用 MySQL"），后续所有增量更新都可能基于这个错误。目前没有主动纠错机制。保守措施是 LLM 调用失败时保持旧摘要不变（而不是编造新内容），以及主题切换时重置。

### Q: 为什么是 3 轮 L1，不是 5 轮？

3 轮是平衡点：足够覆盖指代词（"上次说的那个方案"），不超出模型的注意力衰减范围。每增加 1 轮 L1 就多 ~700 tokens 的 prompt 开销。实测 3 轮 ≈ 2000 tokens 对 64K 上下文窗口完全无压力。

### Q: 画像会不会推断错误？

有可能。LLM 推断的 domain/work_style 不一定准（如被误判为"后端开发者"而实际是全栈）。补偿机制：规则层的置信度机制——不准确的推断置信度低（0.3 以下），不会出现在 format_for_context() 的输出中。
