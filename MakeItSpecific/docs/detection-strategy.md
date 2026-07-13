# 检测体系设计

> 上线后怎么知道系统好不好 — 四条链路 × 三个层级

---

## 总览：四条检测链路

```
┌──────────────────────────────────────────────────────────────────┐
│                        检测体系                                   │
│                                                                   │
│  链路 1: 用户反馈 ──── 👍👎 + 评论 + Badcase 自动标记              │
│  链路 2: 自己使用 ──── 吃自己的狗粮，日常任务全用自己 Agent         │
│  链路 3: 自动监控 ──── 日志驱动，无人值守，异常告警                │
│  链路 4: 主动测试 ──── 固定测试集 + 每次部署跑回归                 │
│                                                                   │
│  每条链路覆盖三个层级:                                              │
│    L1 功能级 — 能不能用                                            │
│    L2 质量级 — 好不好用                                            │
│    L3 体验级 — 用得爽不爽                                          │
└──────────────────────────────────────────────────────────────────┘
```

---

## 链路 1：用户反馈

### 1.1 已做的

| 能力 | 实现 | 状态 |
|------|------|:---:|
| 👍👎 按钮 | FE + POST /api/feedback | ✅ |
| 反馈统计 | GET /api/feedback/stats (按 rating + skill) | ✅ |
| Badcase 标记 | 前端给 👎 消息加 "Badcase" 标签 | ✅ |
| 复盘流程 | docs/badcase-review-guide.md | ✅ |

### 1.2 缺的（上线前应补）

**反馈评论** — 用户点 👎 后弹一个文本框 "哪里不好？"（可选，不强制）。纯负反馈不知道原因，排查靠猜。

```
当前: 👎 → "有人不满意" → 翻日志找原因
期待: 👎 + "生成的提示词版本太多了，只想要一个" → 精准修问题
```

改法：前端 `sendFeedback` 函数在 rating==="negative" 时弹出 `<input>`，POST 时带 `comment` 字段。feedback 表已有 `comment` 字段，只是前端没填。

**反馈率监控** — 如果用户从不点 👍👎，可能是按钮太小、用户没注意到、或者输出质量让用户直接走了。设置一个 "反馈率 = 有反馈的对话 / 总对话" 指标，低于 5% 说明按钮设计有问题。

**Badcase 自动分类** — 不需要用户手动标记。每条 negative 反馈自动关联以下元数据：

```sql
-- 自动关联 badcase 的上下文
SELECT
    f.id,
    f.session_id,
    f.rating,
    s.module as skill,
    s.clarify_rounds,
    s.completeness,
    (SELECT COUNT(*) FROM messages m WHERE m.session_id = f.session_id) as msg_count,
    (SELECT COUNT(*) FROM messages m WHERE m.session_id = f.session_id AND m.msg_type = 'clarify') as clarify_count
FROM feedback f
JOIN sessions s ON f.session_id = s.id
WHERE f.rating = 'negative';
```

这些字段能自动回答：badcase 是发生在追问阶段还是执行阶段？信息完整度够不够？对话长了还是短了？

---

## 链路 2：自己使用（Dogfooding）

### 2.1 核心原则

**你自己的日常任务全部用 MakeItSpecific。** 写提示词 → prompt_refiner。规划任务 → work_arranger。整理文档 → info_retention。审查代码 → code_review。每天至少用 5 次。

### 2.2 具体做法

| 场景 | 用什么 Skill | 怎么评估 |
|------|-------------|---------|
| 写 Portal 的新功能 PRD | work_arranger | 输出的任务拆解合理吗？时间估算准吗？ |
| 给新 feature 写提示词 | prompt_refiner | 生成的提示词实际拿去用了吗？效果好吗？ |
| 整理一次技术讨论 | info_retention | 文档能直接发给别人看吗？ |
| 审查自己刚写的代码 | code_review | 发现了自己没注意到的问题吗？误报多吗？ |

### 2.3 记录方法

建一个简单的 Markdown 日志：

```markdown
## 2026-07-14

### work_arranger — "规划 docs 目录整理"
- 输出质量: 🟢 好 — 阶段划分合理, 时间估算偏乐观
- 追问次数: 1 轮
- 最终采纳: 是, 直接按 plan 执行了

### code_review — "审查 tools/fs.py"
- 输出质量: 🟡 一般 — 发现 2 个真实问题, 但 3 个误报
- 误报: "路径穿越检测不完善" — 实际已覆盖
- 最终采纳: 部分
```

一周后回看这份日志就知道哪些 Skill 稳定、哪些需要修。

### 2.4 自己使用的独特价值

| 外部用户反馈 | 自己使用 |
|-------------|---------|
| "不好用" — 不知道为什么 | 精确知道哪个输出不符合预期 |
| 匿名，无法追问 | 可以自己补日志、补上下文 |
| 样本少，统计意义弱 | 每天 5 次 × 30 天 = 150 次，够做趋势分析 |

---

## 链路 3：自动监控

### 3.1 已有日志信号

| 信号 | 日志 grep | 含义 |
|------|----------|------|
| Planner 降级 | `grep "降级" app.log` | LLM 不稳定 |
| Reflector 不通过 | `grep "Reflector" app.log \| grep -v "LLM 失败"` | 输出质量差 |
| Checkpoint 偏移 | `grep "语义偏移" app.log` | 方向跑偏 |
| RAG 检索失败 | `grep "RAG.*失败\|检索失败" app.log` | 知识库或 API 问题 |
| 工具调用失败 | `grep "\[Tool\].*失败" app.log` | 工具执行异常 |
| Token 异常 | `grep "\[Agent\] done" app.log \| awk -F'tokens=' '{print $2}' \| awk '{if($1>2000) print}'` | 输出过长（可能死循环） |

### 3.2 缺的（上线前应加）

**定时健康检查脚本** — 一个 cron job 每分钟跑一次，不依赖人看日志：

```bash
#!/bin/bash
# scripts/healthcheck.sh — 放到 crontab
HEALTH=$(curl -sf http://localhost/specific/api/health)
if [ $? -ne 0 ]; then
    echo "[ALERT] specific-api down at $(date)" >> /var/log/portal-alerts.log
fi

# Token 异常检测
RECENT=$(docker compose logs --tail=50 specific-api 2>/dev/null)
if echo "$RECENT" | grep -q "\[ERROR\]"; then
    ERROR_COUNT=$(echo "$RECENT" | grep -c "\[ERROR\]")
    if [ $ERROR_COUNT -gt 3 ]; then
        echo "[ALERT] $ERROR_COUNT errors in last 50 log lines at $(date)" >> /var/log/portal-alerts.log
    fi
fi
```

**关键指标仪表盘** — 一个简单的 Python 脚本，输出到终端或导出 JSON：

```python
# scripts/stats.py — 跑在服务器上
import psycopg
from datetime import datetime, timedelta

conn = psycopg.connect("host=localhost dbname=chatdemopg user=postgres ...")

# 过去 24h 的反馈
cur = conn.cursor()
cur.execute("""
    SELECT rating, COUNT(*) FROM feedback
    WHERE created_at > NOW() - INTERVAL '24 hours'
    GROUP BY rating
""")
feedback = dict(cur.fetchall())

# 过去 24h 的对话数
cur.execute("""
    SELECT COUNT(*) FROM sessions
    WHERE updated_at > NOW() - INTERVAL '24 hours'
""")
sessions_24h = cur.fetchone()[0]

# 各 Skill 使用分布
cur.execute("""
    SELECT module, COUNT(*) FROM sessions
    WHERE updated_at > NOW() - INTERVAL '7 days'
    GROUP BY module ORDER BY COUNT(*) DESC
""")
skill_dist = cur.fetchall()

print(f"=== 过去 24h ===")
print(f"对话数: {sessions_24h}")
print(f"反馈: {feedback}")
print(f"\n=== 过去 7 天 Skill 使用 ===")
for skill, count in skill_dist:
    print(f"  {skill}: {count}")

cur.close(); conn.close()
```

输出：
```
=== 过去 24h ===
对话数: 47
反馈: [('positive', 38), ('negative', 3), ('neutral', 6)]

=== 过去 7 天 Skill 使用 ===
  prompt_refiner: 89
  work_arranger: 67
  code_review: 45
  info_retention: 23
```

**Token 消耗趋势** — 每对话平均 token 数有没有上涨？上涨意味着上下文泄漏或 prompt 膨胀：

```bash
grep "\[Agent\] done" data/logs/app.log | \
  awk -F'tokens=' '{print $2}' | awk -F' ' '{print $1}' | \
  awk '{sum+=$1; count++; if($1>max) max=$1; if(min==""||$1<min) min=$1} END {print "avg:", sum/count, "max:", max, "min:", min, "count:", count}'
```

### 3.3 告警阈值建议

| 指标 | 正常 | 警告 | 严重 |
|------|------|------|------|
| Error 率 (最近 1h) | < 1% | 1-5% | > 5% |
| Negative 反馈率 (24h) | < 10% | 10-20% | > 20% |
| 平均 Token/对话 | 300-800 | 800-1500 | > 1500 |
| Planner 降级率 | < 5% | 5-15% | > 15% |
| API 响应时间 P95 | < 5s | 5-15s | > 15s |

---

## 链路 4：主动测试

### 4.1 固定测试集

维护一个 `tests/eval_cases.json`，每次改完代码跑一遍：

```json
[
  {
    "message": "帮我写一个生成产品文案的提示词，面向年轻人的潮牌服饰",
    "expected_skill": "prompt_refiner",
    "checks": ["包含版本号", "包含推荐模型", "有策略说明"]
  },
  {
    "message": "我想用 React 写一个管理后台，大概 50 人使用，三个月搞定",
    "expected_skill": "work_arranger",
    "checks": ["有阶段划分", "有任务清单", "有时间线"]
  },
  {
    "message": "帮我把这次讨论的技术选型决策整理成文档",
    "expected_skill": "info_retention",
    "checks": ["有结构化格式", "有关键决策点"]
  },
  {
    "message": "审查 main.py 的代码质量",
    "expected_skill": "code_review",
    "checks": ["有严重程度分类", "有具体问题描述"]
  }
]
```

跑法：
```bash
python tests/run_eval.py  # 遍历所有 case, 调 API, 检查输出
```

### 4.2 回归维度

| 维度 | 检查方法 | 频率 |
|------|---------|------|
| Router 意图正确 | expected_skill == 实际路由结果 | 每次部署 |
| 输出格式 | checks 里的断言 | 每次部署 |
| 追问是否合理 | 完整度 < 30% 时应返回 clarify | 每次部署 |
| 不崩溃 | 无 ERROR 日志 | 每次部署 |
| Token 不暴涨 | 与上次部署的 avg token 对比，差异 < 30% | 每次部署 |

### 4.3 单元测试（已有）

21 tests, 覆盖 graph 纯函数：维度合并、完整度计算、追问生成、JSON 解析、降级逻辑。每次部署跑 `pytest`。

---

## 四条链路的分工

| | 用户反馈 | 自己使用 | 自动监控 | 主动测试 |
|---|:---:|:---:|:---:|:---:|
| **频率** | 随机 | 每天 | 每分钟 | 每次部署 |
| **覆盖** | 真实场景 | 高频场景 | 系统异常 | 固定基准 |
| **盲区** | 沉默用户 (不点反馈) | 主观偏见 | 语义错误 (不报错但输出错) | 未覆盖的 case |
| **响应速度** | 事后 | 实时 | 实时 | 部署前 |
| **成本** | 零（已有） | 时间 | 脚本+cron | 维护测试集 |

**互补关系**：自动监控抓系统异常（崩溃、超时、死循环）→ 用户反馈抓质量问题（输出不好用）→ 自己使用验证主观体验 → 主动测试守住回归不劣化。

---

## 上线前优先级

| 优先级 | 补什么 | 工作量 | 价值 |
|--------|--------|--------|------|
| **P0** | feedback comment 输入框 | 前端 10 行 JS | 👎 不再是黑盒 |
| **P0** | healthcheck.sh + crontab | 30 行脚本 | 无人值守告警 |
| **P1** | stats.py 统计脚本 | 50 行 Python | 不用翻 DB 看数据 |
| **P1** | 固定 eval_cases.json + run_eval.py | 50 行 + 10 cases | 每次部署自动回归 |
| **P2** | 自己使用日志模板 | 样式模板 | 结构化记录 |
| **P3** | 指标仪表盘 (Grafana?) | 半天 | 可视化看板 |
