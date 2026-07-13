# Badcase 复盘指南

> 如何从用户反馈中发现问题 → 分析根因 → 改进系统

## 1. 什么是 Badcase

用户点了 👎（negative feedback）的那条 AI 回复就是 badcase。它是系统改进最有价值的信号。

## 2. 查找 Badcase

### 2.1 从反馈统计看趋势

```bash
# 查看整体反馈分布
curl http://localhost:8001/api/feedback/stats | python -m json.tool
```

输出示例：
```json
{
  "total": 47,
  "by_rating": {"positive": 38, "negative": 5, "neutral": 4},
  "by_skill": {
    "prompt_refiner": {"positive": 12, "negative": 2, "neutral": 1},
    "work_arranger": {"positive": 15, "negative": 1, "neutral": 2},
    "code_review": {"positive": 8, "negative": 2, "neutral": 1}
  }
}
```

### 2.2 从日志中定位 Badcase

日志位置：`data/logs/app.log`

```bash
# 查看最近的错误和警告
grep -E "\[ERROR\]|\[WARNING\]" data/logs/app.log | tail -50

# 查看 Plannner 降级（信息提取失败的标志）
grep "降级" data/logs/app.log | tail -20

# 查看 Reflector 不通过（质量检查失败的标志）
grep "Reflector" data/logs/app.log | tail -20

# 查看 Checkpoint 语义偏移
grep "语义偏移" data/logs/app.log | tail -20

# 查看工具调用失败的
grep "失败" data/logs/app.log | tail -30
```

### 2.3 从数据库直接查

```sql
-- 找出所有 badcase 的会话
SELECT f.session_id, f.rating, f.created_at, s.module, s.title
FROM feedback f
JOIN sessions s ON f.session_id = s.id
WHERE f.rating = 'negative'
ORDER BY f.created_at DESC;

-- 看某个 badcase 的完整对话
SELECT m.role, m.content, m.created_at
FROM messages m
WHERE m.session_id = 'sess_xxx'
ORDER BY m.created_at ASC;

-- 按 Skill 统计 badcase 率
SELECT
    s.module,
    COUNT(*) FILTER (WHERE f.rating = 'negative') AS bad,
    COUNT(*) FILTER (WHERE f.rating = 'positive') AS good,
    ROUND(COUNT(*) FILTER (WHERE f.rating = 'negative') * 100.0 / COUNT(*), 1) AS bad_rate
FROM feedback f
JOIN sessions s ON f.session_id = s.id
GROUP BY s.module
ORDER BY bad_rate DESC;
```

## 3. 根因分析框架

对每个 badcase，用下列维度诊断：

### 3.1 问题分类树

```
Badcase
├── Planner 问题
│   ├── 意图识别错误（Router 分到了错误的模块）
│   ├── 维度提取不全（用户说了但 LLM 没提取到）
│   ├── 完度判断错误（信息够了还追问 / 不够却直接执行）
│   └── 追问质量差（问题无关联、数量过多、语气冷冰）
│
├── Executor 问题
│   ├── 知识库未命中（该检索的没搜到）
│   ├── 工具调用失败（search_kb 失败 / shell 命令报错）
│   ├── 输出偏离意图（说了用户没问的、漏了用户问了）
│   ├── 格式不佳（没有按要求输出 Markdown / 表格）
│   └── 幻觉（编造了知识库中不存在的信息）
│
├── Checkpoint 问题
│   ├── 语义偏移未拦截（Checkpoint 应该发现但放过了）
│   └── 误拦截（正确输出被判为偏移，触发无意义的 retry）
│
└── Reflector 问题
    ├── 质量差但 score ≥ 7（假阴性 — 没检测到）
    └── 质量好但 score < 7（假阳性 — 误报，浪费 retry）
```

### 3.2 定位方法

| 现象 | 查什么 |
|------|--------|
| "答非所问" | 1) Router 意图是否正确 2) Planner goal 是否偏离 |
| "信息不对" | 1) RAG 检索结果 (`rag_context`) 2) 知识库是否有对应内容 |
| "一直追问" | 1) Planner completeness 2) 维度定义是否合理 |
| "输出太差" | 1) Reflector score 2) 是否触发了 retry |
| "编造信息" | 1) Reflector hallucination_detected 2) 知识库覆盖度 |

## 4. 改进策略

### 4.1 立刻可以做的

| 问题 | 改进 |
|------|------|
| Router 分错模块 | 在 `core/router.py` `_rule_based_route()` 加关键词 |
| 知识库未覆盖 | 在 `knowledge_base/` 补 `.md` 文件 |
| Executor System Prompt 不明确 | 改 `prompts/system_prompts.py` |
| 追问模板不够 | 在 `prompts/templates.py` 补 `CLARIFICATION_TEMPLATES` |

### 4.2 需要更深入分析的

| 问题 | 改进 |
|------|------|
| Planner 频繁降级 | 检查 model 质量、temperature 设置、prompt 是否过时 |
| Checkpoint 频繁误报 | 调整 `PLANNER_CHECKPOINT_PROMPT` 的判断标准 |
| Reflector 假阴性 | 降低 score 阈值或增加审核维度 |
| 某 Skill 的 badcase 率明显高 | 检查该 Skill 的 System Prompt + 工具集是否匹配 |

### 4.3 系统性改进

1. **补知识库** — 大多数"编造信息"问题是因为知识库没覆盖
2. **调 Prompt** — 大多数"输出偏离意图"可以通过更精确的 System Prompt 修正
3. **加示例** — 在 System Prompt 加入期望输出格式的示例（Few-Shot）
4. **增工具** — 如果 Executor 反复问同一个信息，说明缺了一个能获取该信息的 tool

## 5. 复盘流程

每周一次：

1. `GET /api/feedback/stats` → 看趋势（这个月的 badcase 率上升了吗？）
2. SQL 查最近 20 个 negative → 读完整对话 → 逐个分类为上面五类
3. 按 Skill 汇总 → 哪个 Skill badcase 率最高？为什么？
4. 选 3 个最值得修的问题 → 写改进 → 下次复盘验证效果

记录了之后，更新此文档下面的记录：

---

## 复盘记录

### 2026-07-13（初始）

- 反馈系统刚上线，尚无 badcase 数据
- 待积累数据后开始第一轮复盘
