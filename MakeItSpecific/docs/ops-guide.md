# 运维实操手册 — 日志、Badcase、监控

> 从零学会看后台：怎么看日志、怎么定位 badcase、怎么知道系统好不好。
>
> 本文是 [log-management-guide.md](to_log/log-management-guide.md) + [badcase-review-guide.md](to_log/badcase-review-guide.md) + [detection-strategy.md](detection-strategy.md) 的实操整合。读完就能上手。

---

## 目录

1. [日志 — 系统的脉搏](#1-日志--系统的脉搏)
2. [Badcase — 从 👎 到根因](#2-badcase--从--到根因)
3. [四条检测链路全景](#3-四条检测链路全景)
4. [快速排查速查表](#4-快速排查速查表)
5. [已实现 vs 待实现](#5-已实现-vs-待实现)

---

## 1. 日志 — 系统的脉搏

### 1.1 存在哪

```
MakeItSpecific/
└── data/
    └── logs/
        ├── app.log        ← 当前日志（单文件最大 5MB）
        ├── app.log.1      ← 上一个（自动轮转）
        ├── app.log.2      ← 再上一个
        └── app.log.3      ← 最老的（保留 3 个备份）
```

- 配置位置：`app.py` 顶部 `RotatingFileHandler`
- 同时输出到终端（stdout）和文件
- 编码 UTF-8

**本地看**：直接 `tail -f data/logs/app.log`

**Docker 看**：
```bash
docker exec -it specific-api cat /app/data/logs/app.log
docker exec -it specific-api tail -100 /app/data/logs/app.log
```

### 1.2 日志格式

```
07-15 14:32:05 [INFO ] core.agent   | [Memory] L2/L3 记忆系统已初始化
07-15 14:32:07 [INFO ] core.graph   | [Router] scene=prompt_optimize confidence=0.9
07-15 14:32:12 [WARNING] core.graph  | [Planner] LLM 失败，降级
07-15 14:32:15 [ERROR] core.graph   | [Execute] ReAct Agent 失败: timeout
                 │                      │
              日志级别                 模块.代码文件 + 事件描述
```

### 1.3 日志级别：什么要看，什么可以忽略

| Level | 含义 | 要不要管 |
|-------|------|---------|
| `INFO` | 正常流程记录 | 了解系统运行线索即可，不要求每条都看 |
| `WARNING` | 降级/跳过/可恢复的异常 | 看一眼，可能表明配置问题或临时波动 |
| `ERROR` | 调用失败/不可恢复的异常 | **必须排查**，意味着某次用户请求失败了 |

### 1.4 一次对话在日志中的完整链路

用户发送消息后，日志按以下顺序出现：

```
1. [Agent] start session=sess_xxx input_est=4500 module=auto
   → 对话开始，估算输入 token 数

2. [Router] scene=work_plan module=work_arranger confidence=0.9
   → 意图识别完成

3. [ContextEngine] L3 PGVector 检索... / L3 累计事实: ...
   → 上下文引擎工作

4. [Planner] is_complete=true completeness=0.85 goal="..."
   → 维度提取 + 完整度判断完成

5. [Execute] ReAct Agent...
   → 工具调用阶段（可能有多轮 tool call）

6. [Checkpoint] ✅ 语义对齐 (score=8)
   或 [Checkpoint] ❌ 语义偏移 (score=4): ...
   → 语义中枢判断方向对不对

7. [Reflector] score=8 pass=true
   → 质量审查通过（不通过会回到 Execute 重试）

8. [Agent] done session=sess_xxx len=1200 input_est=4500 module=work_arranger intent=工作安排
   → 完成，输出长度 + 意图
```

理解这条链路，你就能通过日志还原任何一次对话的内部决策过程。

### 1.5 各模块日志签名

| 模块 | 搜索关键词 | 看什么 |
|------|-----------|--------|
| `core.agent` | `[Agent]`、`[Memory]` | 流程启动、记忆初始化、token 用量 |
| `core.graph` | `[Router]`、`[Planner]`、`[Execute]`、`[Checkpoint]`、`[Reflector]` | 每一步的决策和执行结果 |
| `core.context_engine` | `[ContextEngine]` | L2 摘要更新、L3 事实提取、话题切换检测 |
| `services.rag_service` | `[RAG]` | 知识库索引、Rerank 耗时与结果 |
| `services.vector_store` | `[PGVector]` | 数据库表创建、向量写入/检索 |
| `tools.*` | `[Tool]` | 工具调用成功/失败详情 |

### 1.6 20 条常用日志命令

```bash
# ═══ 日常监控 ═══

# 1. 实时 tail 日志（最常用，开一个终端一直开着）
tail -f data/logs/app.log

# 2. 看最近 50 条 ERROR + WARNING
grep -E "\[ERROR\]|\[WARNING\]" data/logs/app.log | tail -50

# 3. 只看 ERROR
grep "\[ERROR\]" data/logs/app.log | tail -20

# ═══ 问题定位 ═══

# 4. 追踪某次对话（拿 session_id 精确过滤）
grep "sess_20260715_143200_abc123" data/logs/app.log

# 5. 追踪某个时间段（假定 14:32 前后）
grep "07-15 14:3[2-9]" data/logs/app.log

# 6. 看 Planner 降级频率（LLM 不稳定信号）
grep "降级" data/logs/app.log | tail -20

# 7. 看 Reflector 质量不通过
grep "Reflector" data/logs/app.log | tail -20

# 8. 看 Checkpoint 语义偏移（方向跑偏信号）
grep "语义偏移" data/logs/app.log | tail -20

# 9. 看工具调用失败
grep "\[Tool\]\|失败" data/logs/app.log | tail -30

# 10. 看 Embedding 调用是否正常
grep "Embedding\|embedding" data/logs/app.log | tail -10

# ═══ 性能诊断 ═══

# 11. 看 Rerank 耗时
grep "Rerank" data/logs/app.log | tail -10

# 12. 统计 Planner 降级次数（百分比 = 降级次数/总请求数）
grep "降级" data/logs/app.log | wc -l

# 13. 看平均输出 token 数
grep "\[Agent\] done" data/logs/app.log | awk -F'len=' '{print $2}' | awk '{sum+=$1; count++; if(max=="")max=$1; if($1>max)max=$1; if(min=="")min=$1; if($1<min)min=$1} END {printf "avg=%.0f max=%d min=%d count=%d\n", sum/count, max, min, count}'

# 14. 输出 token 异常检测（单次 > 3000 字符的标出来）
grep "\[Agent\] done" data/logs/app.log | awk -F'len=' '{if($2>3000) print}'

# ═══ 知识库诊断 ═══

# 15. 看索引了多少内容
grep "已索引\|索引" data/logs/app.log | tail -10

# 16. 看检索失败
grep "RAG.*失败\|检索失败\|检索.*失败" data/logs/app.log | tail -10

# ═══ 记忆系统诊断 ═══

# 17. 看 L3 事实提取是否正常
grep "L3" data/logs/app.log | tail -20

# 18. 看话题切换检测
grep "话题切换" data/logs/app.log | tail -10

# ═══ 批量统计 ═══

# 19. 统计各模块日志量分布（看哪个模块最活跃）
grep -oP '\[.*?\]' data/logs/app.log | sort | uniq -c | sort -rn | head -20

# 20. 统计最近 1000 行的日志级别分布
tail -1000 data/logs/app.log | grep -oP '\[(INFO|WARNING|ERROR)' | sort | uniq -c
```

### 1.7 沉默信号 —— 没有日志也是一种信号

有些东西在日志里**完全看不到**本身就是问题：

| 沉默信号 | 意味着什么 |
|----------|-----------|
| 完全没有 `[Memory]` | 记忆系统未启用（检查 `MEMORY_ENABLED` 环境变量） |
| 完全没有 `[RAG]` | 知识库未索引，需要 `POST /api/knowledge/reindex` |
| 完全没有 `[Tool]` | Executor 没调用工具，可能效果不好 |
| 完全没有 `[Checkpoint]` | 正常（意味着没有偏移），但如果同时有大量 badcase 则说明 Checkpoint 漏了 |
| 完全没有 `[ContextEngine]` | 上下文引擎没介入，L2/L3 功能可能失效 |

### 1.8 日志驱动的问题发现 —— 阈值告警

| 信号 | 超过该频率 | 说明 |
|------|-----------|------|
| `Planner LLM 失败` | > 5% 的请求 | LLM 不可靠，检查 API key / 网络 / 余额 |
| `Reflector 不通过` | > 20% 的请求 | 输出质量太差，检查 Executor Prompt |
| `Checkpoint 语义偏移` | > 10% 的请求 | Planner 方向性指导不够，检查 Planner Prompt |
| `Rerank 失败` | 每次检索都失败 | Rerank API 配置问题（DASHSCOPE_API_KEY） |
| `Embedding 失败` | 每次索引都失败 | Embedding API 配置问题 |
| 平均 Token > 1500 | 持续一天 | Prompt 膨胀或输出有冗余，需要检查上下文注入量 |
| Error 率 > 5% | 最近 1 小时 | 有严重 bug 或外部 API 故障 |

---

## 2. Badcase — 从 👎 到根因

### 2.1 什么是 Badcase

用户点了 👎（negative feedback）的那条 AI 回复。**它是系统改进最有价值的信号** — 比任何监控指标都直接。

### 2.2 从哪些渠道找 Badcase

#### 方式一：API（最方便）

```bash
# 整体反馈分布
curl http://localhost:8001/api/feedback/stats | python -m json.tool

# 按 Skill 过滤
curl "http://localhost:8001/api/feedback/stats?skill=work_arranger" | python -m json.tool
```

输出示例：
```json
{
  "total": 47,
  "by_rating": {"positive": 38, "negative": 5, "neutral": 4},
  "by_skill": {
    "prompt_refiner": {"positive": 12, "negative": 2, "neutral": 1},
    "work_arranger": {"positive": 15, "negative": 1, "neutral": 2}
  }
}
```

#### 方式二：SQL 直接查（最精确）

```sql
-- 列出所有 badcase 会话
SELECT f.id, f.session_id, f.rating, f.created_at, s.module, s.title
FROM feedback f
JOIN sessions s ON f.session_id = s.id
WHERE f.rating = 'negative'
ORDER BY f.created_at DESC
LIMIT 20;

-- 看某个 badcase 的完整对话（复制上面的 session_id）
SELECT m.role, m.msg_type, m.content, m.created_at
FROM messages m
WHERE m.session_id = 'sess_xxx'
ORDER BY m.created_at ASC;

-- 按 Skill 统计 badcase 率
SELECT
    s.module,
    COUNT(*) AS total,
    COUNT(*) FILTER (WHERE f.rating = 'negative') AS bad,
    ROUND(
        COUNT(*) FILTER (WHERE f.rating = 'negative') * 100.0 / COUNT(*), 1
    ) AS bad_rate_pct
FROM feedback f
JOIN sessions s ON f.session_id = s.id
GROUP BY s.module
ORDER BY bad_rate_pct DESC;
```

#### 方式三：日志里找（辅助）

```bash
# Checkpoint 被触发的（说明有语义偏移）
grep "语义偏移" data/logs/app.log | tail -20

# Reflector 不通过的（说明输出质量差）
grep "Reflector" data/logs/app.log | tail -20
```

### 2.3 Badcase 根因分类框架

拿到一个 badcase 后，按以下决策树分类：

```
用户说 "答非所问" ──→ Router 意图是否正确？──→ 否 → Router 问题（补关键词）
                    └─→ 是 → Planner goal 是否偏离？──→ 是 → Planner 问题（调 prompt）

用户说 "信息不对" ──→ 知识库有对应内容吗？──→ 没有 → 补 knowledge_base/ 下的 .md
                    └─→ 有 → RAG 检索到了吗？──→ 没有 → RAG 检索问题（调 query 增强）

用户说 "一直追问" ──→ Planner completeness 是多少？──→ < 50% → 维度定义可能太细
                                                      └─→ > 70% → Planner 完整度判断有 bug

用户说 "输出太差" ──→ Reflector score 是多少？──→ ≥ 7 → Reflector 假阴性（漏判）
                                               └─→ < 7 → 触发了 retry 吗？──→ 没触发 → 路由逻辑 bug

用户说 "编造信息" ──→ Reflector hallucination_detected 是什么？──→ false → 幻觉检测漏了
                                                                 └─→ true → 知识库覆盖不
```

### 2.4 完整分类树

```
Badcase
├── Planner 问题
│   ├── 意图识别错误（Router 分到了错误的模块）
│   ├── 维度提取不全（用户说了但 LLM 没提取到）
│   ├── 完整度判断错误（信息够了还追问 / 不够却直接执行）
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
    ├── 质量差但 score ≥ 7（假阴性 — 没检测到问题）
    └── 质量好但 score < 7（假阳性 — 误报，浪费一次 retry）
```

### 2.5 定位速查表

| 现象 | 第一步查什么 | 第二步查什么 |
|------|-------------|-------------|
| "答非所问" | Router 意图 → `grep "Router" app.log` | Planner goal 是否偏离用户原始消息 |
| "信息不对" | RAG 检索结果 → `grep "RAG" app.log` | 知识库里有对应内容吗 |
| "一直追问" | Planner completeness 值 | 维度定义是否合理（`prompts/templates.py`） |
| "输出太差" | Reflector score 值 | 是否触发了 retry |
| "编造信息" | Checkpoint hallucination_detected | 知识库覆盖度 |
| "一直打转" (死循环) | tool call 轮数 → `grep "Tool" app.log` | 防循环三层防线是否生效 |

### 2.6 修复优先级

#### 立刻可以改的（改完重启即可验证）

| 问题 | 改哪里 |
|------|--------|
| Router 分错模块 | `core/router.py` → `_rule_based_route()` 加关键词 |
| 知识库未覆盖 | `knowledge_base/` 下补 `.md` 文件 |
| Executor 指令不明确 | `prompts/system_prompts.py` → 改 EXECUTOR_SYSTEM_PROMPT |
| 追问模板不够 | `prompts/templates.py` → 补 `CLARIFICATION_TEMPLATES` |
| 工具描述不精准 | 对应工具的 docstring（三段式中的【不要用】部分） |

#### 需要实验验证的（改完要多跑几个 case 确认效果）

| 问题 | 改哪里 | 风险 |
|------|--------|------|
| Planner 频繁降级 | 换 model / 调 temperature | 可能影响其他 Skill |
| Checkpoint 频繁误报 | 调 `PLANNER_CHECKPOINT_PROMPT` 的判断标准 | 放宽可能导致真正的偏移漏过 |
| Reflector 假阴性 | 降低 score 阈值或增加审核维度 | 更严格的阈值意味着更多 retry |
| 某 Skill badcase 率明显高 | 检查该 Skill 的 System Prompt + 工具集是否匹配 | 可能需要重新设计工具映射 |

### 2.7 每周复盘流程

```
1. curl /api/feedback/stats → 看趋势
   - badcase 率上升了吗？（和上周比）
   - 哪个 Skill 的 badcase 率最高？

2. SQL 查最近 20 个 negative → 读完整对话 → 逐个分类为上面的分类框架
   - 不需要每个都修，只需要找到反复出现的模式

3. 按 Skill 汇总 → 按 badcase 率排序
   - badcase 率 > 20% 的 Skill 需要优先处理

4. 选 3 个最值得修的问题
   - 选"频率最高"的而不是"最严重的"
   - 频率高的修一次影响面最大

5. 写改进 → 部署 → 下次复盘验证效果
```

### 2.8 Badcase 存储规范

所有 badcase 应存入 `tests/badcase_regression.jsonl`：

```jsonl
{"id":"bc_001","input":"帮我写个提示词","expected_module":"prompt_refiner","actual_module":"work_arranger","type":"router_misclassify","severity":"high"}
{"id":"bc_002","input":"React 18 Suspense 怎么用","expected_output_contains":"Suspense","actual_output":"（讲了一堆 Vue 的东西）","type":"rag_hallucination","severity":"high"}
{"id":"bc_003","input":"用 React 写博客","output_contains":"推荐 Redux","type":"l3_fact_miss","severity":"medium","note":"L3 有事实'用户不要 Redux'但未召回"}
```

类型字段：
- `router_misclassify` — Router 分错了模块
- `rag_hallucination` — RAG 结果导致的幻觉
- `planner_under_extract` — Planner 维度提取不足
- `execute_tool_loop` — Executor 工具调用死循环
- `checkpoint_miss` — Checkpoint 漏拦截语义偏移
- `reflector_false_negative` — Reflector 假阴性
- `l3_fact_miss` — L3 事实未召回
- `intent_drift` — 意图偏移

---

## 3. 四条检测链路全景

### 3.1 链路总览

```
┌─────────────────────────────────────────────────────────────┐
│                      检测体系                                │
│                                                              │
│  链路 1: 用户反馈 ── 👍👎 + 评论 + Badcase 自动标记          │
│  链路 2: 自己使用 ── 吃自己的狗粮，日常任务全用自己 Agent     │
│  链路 3: 自动监控 ── 日志驱动，无人值守，异常告警            │
│  链路 4: 主动测试 ── 固定测试集 + 每次部署跑回归             │
│                                                              │
│  每条链路覆盖三个层级:                                        │
│    L1 功能级 — 能不能用                                      │
│    L2 质量级 — 好不好用                                      │
│    L3 体验级 — 用得爽不爽                                    │
└──────────────────────────────────────────────────────────────┘
```

### 3.2 四条链路的分工

| | 用户反馈 | 自己使用 | 自动监控 | 主动测试 |
|---|:---:|:---:|:---:|:---:|
| **频率** | 随机 | 每天 | 每分钟 | 每次部署 |
| **覆盖** | 真实场景 | 高频场景 | 系统异常 | 固定基准 |
| **盲区** | 沉默用户 | 主观偏见 | 语义错误 | 未覆盖的 case |
| **响应速度** | 事后 | 实时 | 实时 | 部署前 |
| **成本** | 零 | 时间 | 脚本+cron | 维护测试集 |

**互补关系**：
- **自动监控** → 抓系统异常（崩溃、超时、死循环）
- **用户反馈** → 抓质量问题（输出不好用）
- **自己使用** → 验证主观体验（颗粒度最细）
- **主动测试** → 守住回归不劣化（每次部署的门槛）

---

## 4. 快速排查速查表

> 用户反馈 / 自己发现一个问题 → 从左边找到现象 → 按箭头方向排查

```
"服务挂了 / 页面打不开"
   → docker compose ps（容器还在吗？）
   → docker compose logs specific-api | tail -50（最后 50 行有什么？）
   → grep "\[ERROR\]" data/logs/app.log | tail -20（最新的错误是什么？）
   → curl http://localhost:8001/api/health（API 还活着吗？）

"回答很慢 / 超时"
   → grep "Rerank" data/logs/app.log（Rerank 耗时正常吗？）
   → grep "\[Execute\]" data/logs/app.log（Executor 跑了几轮 tool call？）
   → grep "timeout\|超时" data/logs/app.log（有没有超时日志？）
   → curl http://localhost:8001/api/health（API 响应时间多少？）

"输出质量突然变差"
   → grep "降级" data/logs/app.log（Planner/Executor 是否频繁降级？）
   → grep "Reflector" data/logs/app.log（Reflector 是不是一直不通过？）
   → 对比改代码前后的日志，看哪个节点的输出变了

"知识库查不到内容"
   → grep "RAG" data/logs/app.log | tail -10（检索是否执行？）
   → grep "rerank\|Rerank" data/logs/app.log（Rerank 是否失败？）
   → POST /api/knowledge/reindex（重建索引试试）
   → 检查 knowledge_base/ 下是否有对应 .md 文件

"记忆系统不工作"
   → grep "\[Memory\]" data/logs/app.log（初始化成功了吗？）
   → grep "L3" data/logs/app.log（事实提取在执行吗？）
   → 检查 MEMORY_ENABLED 环境变量
   → 检查 PGVector session_memory 表是否有数据

"工具调用一直失败"
   → grep "\[Tool\].*失败" data/logs/app.log（具体哪个工具失败了？）
   → 检查对应工具的 API key（Tavily / DASHSCOPE 等）
   → 检查工具代码里的 async/await 是否匹配（参考 debug-report 的 Bug 3）

"前端一直转圈没有输出"
   → grep "Graph 执行失败" data/logs/app.log（Graph 层异常？）
   → grep "\[Agent\] done" data/logs/app.log（Agent 有没有正常结束？）
   → 检查浏览器 Network 面板的 SSE 连接状态
```

---

## 5. 已实现 vs 待实现

### 5.1 工具层面

| 功能 | 状态 | 位置 |
|------|:---:|------|
| RotatingFileHandler 日志轮转（5MB×4） | ✅ | `app.py:14-24` |
| 日志双写（终端 + 文件） | ✅ | `app.py:20-23` |
| 各模块日志签名（[Agent]/[Router]/[Planner] 等） | ✅ | 全链路 |
| 👍👎 反馈按钮 + 前端 Badcase 标签 | ✅ | `static/js/chat.js:241-268` |
| 反馈 API：POST + GET /stats | ✅ | `routers/feedback.py` |
| SQLite feedback 表（rating+comment+skill） | ✅ | `services/session_store.py:87-95` |

### 5.2 待实现（按优先级）

| 优先级 | 功能 | 做什么 | 预估 |
|--------|------|--------|------|
| 🔴 P0 | **Badcase 自动保存** | Reflector score<5 / Checkpoint aligned=false / 👎 → 完整上下文存档到 JSONL | ~80 行 |
| 🔴 P0 | **feedback comment 输入框** | 👎 后弹文本框"哪里不好？"，`comment` 字段已建好只是前端没填 | ~15 行 JS |
| 🔴 P0 | **healthcheck.sh** | cron 每分钟检测 API 存活 + Error 数量告警 | ~30 行 shell |
| 🟡 P1 | **stats.py 统计脚本** | 查看过去 24h 对话数/反馈数/各 Skill 使用分布 | ~50 行 Python |
| 🟡 P1 | **eval_cases.json + run_eval.py** | 10 个固定用例，每次部署自动回归（Router 正确率 + 输出格式检查） | ~100 行 |
| 🟡 P1 | **Token 用量监控** `obs/token_tracker.py` | 实时统计每天/每周的 token 消耗 | ~60 行 |
| 🟡 P1 | **循环检测硬计数器** | 同一 query 反复调同一 tool → 强制终止 | ~40 行 |
| 🟢 P2 | **Badcase 分析 dashboard** | 反馈数据可视化（按 skill/时间/类型的 badcase 趋势） | ~100 行 |
| 🟢 P2 | **自己使用日志模板** | 结构化记录自己每天使用各 Skill 的质量评分 | ~30 行 Markdown |

---

## 附录 A：本地开发时的实时监控工作流

```bash
# 终端 1：跑服务
cd ~/portal/MakeItSpecific
python app.py

# 终端 2：实时 tail 日志
cd ~/portal/MakeItSpecific
tail -f data/logs/app.log

# 终端 3：偶尔查看统计
watch -n 30 'curl -s http://localhost:8001/api/feedback/stats | python -m json.tool'
```

边在前端操作，边看终端 2 的日志滚动 —— 这是最快的学习方式。

## 附录 B：服务器部署后的日常命令

```bash
cd ~/portal

# 看所有容器状态
docker compose ps

# 看 MakeItSpecific 实时日志
docker compose logs -f specific-api

# 看最近 100 行
docker compose logs --tail=100 specific-api

# 只过滤错误
docker compose logs specific-api 2>&1 | grep -E "\[ERROR\]|\[WARNING\]"

# 进入容器直接操作
docker exec -it specific-api bash
# 进去后:
#   cat /app/data/logs/app.log          — 完整日志
#   tail -100 /app/data/logs/app.log    — 最近 100 行

# 检查 API 是否存活
curl http://localhost/specific/api/health

# 看反馈统计
curl http://localhost/specific/api/feedback/stats | python -m json.tool
```

## 附录 C：相关文档索引

| 文档 | 内容 |
|------|------|
| [log-management-guide.md](to_log/log-management-guide.md) | 日志系统的详细设计（轮转策略、格式、存储管理） |
| [badcase-review-guide.md](to_log/badcase-review-guide.md) | Badcase 复盘流程的原始版本 |
| [detection-strategy.md](detection-strategy.md) | 四条检测链路的架构设计 + 告警阈值 |
| [hallucination-prevention.md](done/hallucination-prevention.md) | 五层幻觉防御 + Badcase 自动保存设计 |
| [debug-report-2026-07-14.md](to_log/debug-report-2026-07-14.md) | 真实 debug 全链路记录（4 个 bug 的排查过程） |
| [boundary.md](../boundary.md) | 约束规范与检查清单（Harness Engineering 落地文件） |
| [PROGRESS.md](../PROGRESS.md) | 项目进度总结 + 待做事项 |
