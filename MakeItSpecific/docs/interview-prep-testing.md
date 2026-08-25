# 测试面试试训文档 — 基于 Alfred (Portal) 项目实战

> 以真实项目经历回答测试面试中的高频问题：你们怎么测的？遇到过什么 bug？边界怎么处理的？案例从哪来？

---

## 一、项目测试体系总览

### 1.1 我们做了什么

```
                    ┌──────────────────────────┐
                    │     Alfred 测试体系        │
                    │                          │
                    │  单元测试 ── 25 tests     │
                    │  集成测试 ── DB 直连       │
                    │  回归检测 ── 四条链路      │
                    │  边界测试 ── 降级+兜底     │
                    │  案例挖掘 ── Dogfooding   │
                    └──────────────────────────┘
```

| 层级 | 覆盖内容 | 文件 | 数量 |
|------|---------|------|------|
| 单元测试 | 维度合并、完整度计算、追问生成、JSON 解析、降级逻辑 | `tests/test_graph.py` | 21 |
| 集成测试 | Session CRUD、消息读写、级联删除、反馈统计 | `tests/test_session_store.py` | 5 |
| 回归检测 | 四条链路（用户反馈+自己使用+自动监控+主动测试） | `docs/detection-strategy.md` | 体系文档 |
| 边界/异常 | 故障注入 + 降级策略 | 代码内嵌 | 10+ 处 |

### 1.2 项目特点决定了测试策略

Alfred 是一个 **LLM Agent 项目**，它跟传统 CRUD 项目有一个根本区别：

```
传统项目:  输入 A → 代码逻辑 → 输出 B   (确定性)
LLM Agent: 输入 A → LLM → 输出 B'      (非确定性，每次结果可能不同)
```

所以我们的测试策略是 **"测确定性部分，监控非确定性部分"**：

- **确定性部分**（纯函数逻辑）→ 单元测试，assert 精确值
- **非确定性部分**（LLM 输出）→ 结构校验 + 降级兜底 + 人工反馈 + 自动监控

---

## 二、我们测了什么（具体代码）

### 2.1 维度合并逻辑（最核心的纯函数）

Planner 节点用 LLM 提取任务维度（目标、时间、技术栈等），然后合并到已有维度。合并规则是**高置信度覆盖低置信度**——这是整个 Agent 正确性的基础，必须精确测试。

```python
# tests/test_graph.py
class TestDimensionMerging:
    def test_merge_overwrites_lower_confidence(self):
        """低置信度应被高置信度覆盖"""
        existing = {"purpose": "模糊描述", "purpose_confidence": 0.3}
        extracted = {"purpose": {"value": "清晰描述", "confidence": 0.9}}
        merged = _merge_dimensions_from_plan(existing, extracted)
        assert merged["purpose"] == "清晰描述"

    def test_merge_keeps_higher_confidence(self):
        """高置信度不应被低置信度覆盖"""
        existing = {"purpose": "已确认描述", "purpose_confidence": 0.95}
        extracted = {"purpose": {"value": "新提取但低置信", "confidence": 0.4}}
        merged = _merge_dimensions_from_plan(existing, extracted)
        assert merged["purpose"] == "已确认描述"  # 保持不变

    def test_merge_with_string_values(self):
        """兼容性：LLM 可能返回字符串而非 dict"""
        extracted = {"purpose": "做翻译"}  # 直接字符串，不是 {value, confidence}
        merged = _merge_dimensions_from_plan({}, extracted)
        assert merged["purpose"] == "做翻译"

    def test_merge_skips_null_values(self):
        """LLM 可能返回 null value"""
        extracted = {"purpose": {"value": None, "confidence": 0}}
        merged = _merge_dimensions_from_plan({}, extracted)
        assert "purpose" not in merged or merged.get("purpose") is None
```

**面试要点**：这里体现了 LLM Agent 项目的典型测试思维——"LLM 输出不可靠，所以合并逻辑必须能处理各种异常格式（dict/string/null）"。

### 2.2 完整度计算

用户输入的信息够不够？不够就要追问。这个阈值判断影响整个对话流程。

```python
class TestCompleteness:
    def test_empty_score_zero(self):
        """什么都没填 → 完整度 0%"""
        score, gaps = calculate_completeness({}, MODULE_DIMENSIONS["prompt_refiner"])
        assert score == 0.0
        assert len(gaps) > 0

    def test_partial_score(self):
        """填了一部分 → 完整度在 30%-80% 之间"""
        expressed = {"purpose": "优化提示词", "purpose_confidence": 0.9}
        score, gaps = calculate_completeness(expressed, MODULE_DIMENSIONS["prompt_refiner"])
        assert 0.3 < score < 0.8

    def test_full_score(self):
        """全填了 → 完整度 > 90%"""
        expressed = {key: "填好了" for key in MODULE_DIMENSIONS["info_retention"]}
        for key in expressed:
            expressed[f"{key}_confidence"] = 1.0
        score, gaps = calculate_completeness(expressed, MODULE_DIMENSIONS["info_retention"])
        assert score > 0.9
```

**面试要点**：边界测试不是只测 0 和 1，中间状态（30%-80%）才是最容易出 bug 的地方。

### 2.3 JSON 解析鲁棒性

LLM 输出的 JSON 不可靠——可能包裹在 markdown code block 里、可能是纯文本、可能是空字符串。解析器必须全部兜住。

```python
class TestPlannerJSONParsing:
    def test_parse_valid_json(self):          # 正常 JSON
    def test_parse_json_in_code_block(self):   # ```json ... ``` 包裹
    def test_parse_malformed_json(self):       # 纯文本 "这不是 JSON"
    def test_parse_empty_string(self):         # 空字符串

class TestReflectionJSONParsing:
    def test_parse_malformed(self):
        result = _parse_reflection_json("not json")
        assert result["pass"] is True  # 出错了默认通过，不阻断流程
```

**设计决策**：Reflector 解析失败时默认 `pass=True`，这是故意的——"宁可放过一个质量一般的输出，也不能因为解析错误把用户卡死"。这是一个 trade-off，面试时如果能说清楚 why 会加分。

### 2.4 集成测试（PostgreSQL 直连）

不 mock 数据库，直接连真实 PostgreSQL。条件跳过（没有 PG 时自动 skip）。

```python
@pytest.mark.skipif(not _pg_available(), reason="PostgreSQL 不可用，跳过")
class TestSessionStorePG:
    def test_delete_session_cascade(self):
        """删除 Session 时消息也必须级联删除"""
        store = SessionStore(conn_string)
        sid = store.create_session(module="info_retention")
        store.save_message(sid, "user", "test", "input")
        assert len(store.get_conversation(sid)) == 1
        store.delete_session(sid)
        assert store.get_session(sid) is None
        assert len(store.get_conversation(sid)) == 0  # cascade 生效
```

---

## 三、遇到过的最大的 Bug

### 3.1 语义偏移（Semantic Drift）— 最深刻的一个

**现象**：用户说"帮我做一个论坛"，Alfred 没有写代码，而是输出了一份"如何开发论坛的策略提示词"。

**排查过程**：

```
1. 看日志 → Planner 正确识别 intent: "搭建论坛项目", module: work_arranger
2. 看 Executor 输出 → 生成的是三个"开发论坛的 prompt 策略"，不是代码
3. 看 Checkpoint 日志 → "语义偏移 score=2: 输出内容完全偏离了用户意图"
4. 看重试后 → Executor 再次输出类似的策略文档（没变！）
```

**根因**：

```
Planner (JSON mode)            Executor (ReAct Agent)
───────────────────            ──────────────────────
goal: "搭建一个论坛"    ──→    System Prompt: WORK_ARRANGER_SYSTEM
execution_plan: [...]          倾向: "先规划再行动"
                               实际行为: 写出"策略提示词"而非写代码
                               
问题: 两个 Prompt 之间只有语义传递，没有硬约束。
Planner 说"动手做"，Executor 理解成"先规划怎么做"。
```

**修复了什么**：

1. **加 Checkpoint 节点** — Executor 输出后，再用 LLM 检查一次是否语义对齐
2. **限制重试次数** — `MAX_CHECKPOINT_RETRIES = 1`，发现偏移后最多给 Executor 一次修正机会
3. **兜底放行** — 重试后仍偏移 → 放弃纠正，进 Reflector 做最终质量判断
4. **日志留痕** — 每次偏移都打 `[Checkpoint] ❌ 语义偏移` 日志，方便事后分析

**教训**：

> 多节点 LLM Agent 中，不同节点的 Prompt 方向不一致会导致"传话游戏"式的语义衰减。这不是传统意义上的 bug——代码没有错，LLM 也没有报错——但系统行为不符合预期。这类问题的测试不能靠单元测试，要靠**端到端的回归案例**。

### 3.2 工具死循环 — Agent 搜了 8 次同一个东西

**现象**：Agent 在 ReAct 循环中调用 `search_web("React Suspense")` → `search_web("React Suspense 用法")` → `search_web("React Suspense how to use")` → ...，换汤不换药地搜了 8 次。

**根因**：只有**全局 10 轮上限**做兜底，没有**工具级上限**和**去重检测**。Agent 以为"再搜一次就能找到"。

**已做的防护**：
- `DEFAULT_MAX_TOOL_ROUNDS = 10`（全局硬上限）
- System Prompt 写入"最多 10 轮，超过必须输出"

**识别到但尚未实施的防护**（设计文档已写完）：
- 工具指纹去重：`search_web("React Suspense")` 和 `search_web("React Suspense 怎么用")` → 同一指纹
- 工具级上限：`search_web ≤ 5`, `fetch_url ≤ 3`, `delegate_task ≤ 1`
- 摇摆检测：A→B→A→B 模式识别
- 信息增益检查：新搜索结果 85% 关键词和之前重叠 → 停止

### 3.3 SQL 模板占位符冲突 — 最隐蔽的一个

**Commit**: `791bd28`

**现象**：PostgreSQL 启动时 `ensure_tables` 报错，SQL 执行失败。

**根因**：

```python
# SQL 模板中的 JSONB 默认值 '{}' 被 psycopg 的 sql.SQL.format 误解析为占位符
# '{}' 在 Python format 语法中是空 dict 占位符！
# 修复: 转义为 '{{}}'
```

这类 bug 的典型特征：**代码没有语法错误，SQL 单独执行也对，但组合起来就炸**。特点是：
- 错误信息不直观（`format() got unexpected keyword` 之类的）
- 只在特定执行路径触发（生产环境有、本地没有）
- 涉及两个系统的交互边界（Python format 语法 × SQL 语法）

### 3.4 Nginx 子路径部署 — 最折腾的一个

**现象**：Alfred 通过 Portal 的 nginx 代理访问时，页面空白，CSS/JS 全部 404。

**根因链**：
1. HTML 中 `<link href="css/style.css">` 是相对路径
2. 浏览器当前 URL 是 `https://yoiwerr.site/alfred/`
3. 浏览器解析出 `https://yoiwerr.site/css/style.css` → 404
4. 正确路径应该是 `https://yoiwerr.site/alfred/css/style.css`

**三阶段修复**：
- Round 1：前端全部改用相对路径 `href="css/style.css"`（去掉前导 `/`）
- Round 2：注入 `<base href="/alfred/">` 到 HTML
- Round 3：nginx 用 standard prefix-strip 写法替代变量 + rewrite

**教训**：子路径部署的测试不能只测根路径，要实际通过 nginx 代理访问验证。

---

## 四、边界怎么测的

### 4.1 LLM 输出格式的边界

LLM 不是 API，输出格式不可靠。我们的策略是 **"永远假设 LLM 会返回脏数据"**：

```python
# 从 graph.py 中提取的降级处理模式

# 边界 1: Planner LLM 挂了 → 规则降级
try:
    plan = _parse_planner_json(response.content)
except Exception:
    plan = _fallback_plan(user_message, dims)  # 纯规则兜底

# 边界 2: JSON 解析失败 → 提供默认值
result = _parse_planner_json(raw)
# 内部: 先 strip, 再试 json.loads, 再试正则提取 ```json...```, 
#       都失败则返回 {"is_complete": False, "completeness": 0.0}

# 边界 3: Reflector LLM 挂了 → 默认通过（不阻断用户）
try:
    reflection = _parse_reflection_json(response.content)
except Exception:
    reflection = {"pass": True, "score": 7}  # 宁可放过，不可错杀

# 边界 4: Contract 解析失败 → 手动构建 dict
try:
    contract = Contract.model_validate_json(raw)
except Exception:
    contract = _build_fallback_contract(raw)  # 逐字段提取
```

### 4.2 对话流程的边界

```python
# 追问轮数上限
DEFAULT_MAX_CLARIFY_ROUNDS = 3  # 超过 3 轮追问 → 强制执行

# ReAct 工具调用上限
DEFAULT_MAX_TOOL_ROUNDS = 10    # 超过 10 轮 → 强制输出

# 质量检查重试上限
MAX_REFLECTION_RETRIES = 2      # Reflector 最多拒 2 次
MAX_CHECKPOINT_RETRIES = 1      # Checkpoint 最多修正 1 次

# 短消息 → 直接追问
def _fallback_plan(msg, dims):
    if len(msg) < 20:            # 太短了，肯定信息不够
        return {"is_complete": False, "clarify_questions": [...]}
```

### 4.3 数据库/服务启动的边界

```python
# app.py — lifespan 中的优雅降级
try:
    agent = Agent(...)
except Exception as e:
    print(f"[FAIL] 启动失败 (部分功能不可用): {e}")
    # 不抛异常 — agent 保持 None，端点返回 503

# 健康检查暴露降级状态
@app.get("/api/health")
async def health():
    degraded = not deps["postgres"] or not deps["agent"]
    return JSONResponse(
        content={"status": "degraded" if degraded else "ok", "deps": deps},
        status_code=503 if degraded else 200,
    )
```

**设计理念**：启动时一个依赖挂了 ≠ 整个服务不可用。健康检查告诉你哪些降级了，nginx 根据健康状态决定是否路由流量。

### 4.4 跨语言边界（Go ↔ Python）

Go 签发 JWT → Python 自验。边界测试点：

```python
# routers/deps.py
async def get_current_user(credentials):
    if credentials is None:
        return None        # 边界 1: 无 token → None，不抛异常
    
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return None        # 边界 2: 过期/无效 → None，端点自行决定是否拒绝
```

```go
// internal/service/auth.go — Go 侧
func (s *AuthService) RefreshAccessToken(ctx context.Context, refreshToken string) (*TokenPair, error) {
    // 边界 3: Refresh Token 轮换 — 先用旧 token 查用户，签发新 token 同时 revoke 旧的
    _, _ = s.db.Exec(ctx, `UPDATE admin_refresh_tokens SET revoked = true WHERE token_hash = $1`, tokenHash)
    return s.generateTokenPair(ctx, user)
}
```

---

## 五、测试案例怎么找的

### 5.1 方法一：从 LLM 的"不听话"中找

这是 LLM Agent 项目最独特的案例来源。不是从需求文档推导，而是**观察模型实际输出中的意外行为**。

```
来源: 看日志 → 发现 Executor 输出的是"策略文档"而非代码
案例: "帮我做一个论坛" 预期是生成项目文件，实际是输出开发建议
测试: 加入回归 case，每次部署后验证 intent → execution 链
```

### 5.2 方法二：Dogfooding（吃自己的狗粮）

```
原则: 自己的日常任务全用 Alfred
频率: 每天至少 5 次
产出: 每次使用记录输出质量和遇到的问题

例:
  work_arranger — "规划 docs 目录整理"
  - 输出质量: 🟢 好 — 阶段划分合理
  - 追问次数: 1 轮
  - 最终采纳: 是

  code_review — "审查 tools/fs.py"
  - 输出质量: 🟡 一般 — 发现 2 个真实问题, 但 3 个误报
  - 误报: "路径穿越检测不完善" — 实际已覆盖
```

### 5.3 方法三：从部署事故反推

| 部署事故 | 根因 | 新增测试/防护 |
|---------|------|-------------|
| Docker 启动崩溃 | pgvector 扩展未提前创建 | `ensure_tables` 先 `CREATE EXTENSION` |
| Nginx 代理后 CSS 404 | 相对路径解析错误 | 全部改用相对路径 + `<base href>` |
| 容器重建后 502 | nginx DNS 缓存过期 | `proxy_pass` 用变量动态解析 |
| SQL 模板报错 | `{}` 被 format 误解析 | 转义 `{{}}` + 回归测试 |
| 启动即死 | `start_period` 太短(15s) | 改为 90s + 健康检查等 DB 就绪 |

### 5.4 方法四：四个维度的回归检测

我们设计了一套检测体系（见 `docs/detection-strategy.md`），不是传统意义上的"测试用例"，更像是**持续质量保障的四个视角**：

| 链路 | 频率 | 覆盖 | 盲区 |
|------|------|------|------|
| **自动监控** | 每分钟 | 系统异常（崩溃/超时/死循环） | 语义错误（不报错但输出错） |
| **用户反馈** | 随机 | 真实场景 | 沉默用户（不点 👎） |
| **自己使用** | 每天 | 高频场景 | 主观偏见 |
| **主动测试** | 每次部署 | 固定回归基准 | 未覆盖的 case |

### 5.5 方法五：从极限值推导

这是传统的边界值分析法，对纯函数尤其有效：

```python
# 完整度计算 → 三个关键点
score == 0.0    # 什么都没填
0.3 < score < 0.8  # 填了一部分（最复杂、最容易出 bug 的区间）
score > 0.9     # 全填了

# 追问生成 → 两个约束
questions_with_full_context < questions_with_empty_context  # 已有信息越多，追问越少
all(q["dimension"] != "purpose" for q in questions)          # 已填的维度不应再问

# JSON 解析 → 四种异常
valid_json       # 正常
markdown_wrapped # ```json ... ```
plain_text       # "这不是 JSON"
empty_string     # ""
```

---

## 六、如果面试官问"你觉得测试够吗"

**诚实回答**：不够。我们当前有 25 个测试，覆盖了核心纯函数和 DB 集成，但以下方面有明显缺口：

| 缺口 | 现状 | 为什么没做 | 如果做会怎么做 |
|------|------|-----------|--------------|
| **Go 后台测试** | 0 tests | AlfredAdmin 是新增的，先跑通功能 | `go test` + testify，测 handler→service→store 全链路 |
| **LLM 输出回归** | 无自动化 | 每次调 prompt 都要手工验证 | `eval_cases.json` + `run_eval.py`，10 个固定 case 每次部署跑 |
| **SSE 流式测试** | 无 | async generator 测试难写 | `httpx.AsyncClient` + `iter_lines()` 验证 SSE 事件序列 |
| **Nginx 路由回归** | 无 | 靠手工 curl | 写一个 `test_routes.sh`，逐条验证 HTTP 状态码 |
| **性能基准** | 无 | 目前用户只有自己 | `pytest-benchmark` 或 locust，监控 token 消耗趋势 |

**关键认知**：测试投入要和项目阶段匹配。个人项目 25 个测试 + 四条检测链路已经足够，但如果有外部用户，LLM 输出回归是第一个要补的。

---

## 七、面试中可能被追问的问题

### Q1: "你测了 LLM 的输出，但 LLM 输出是不确定的，怎么 assert？"

**答**：我们不对 LLM 的**内容**做精确 assert，而是测三个东西：

1. **结构** — Planner 输出必须是合法 JSON，有 `is_complete` 和 `completeness` 字段
2. **兜底** — JSON 解析失败时降级逻辑是否生效（`test_parse_malformed_json`）
3. **统计** — 通过用户反馈（👍👎）和自动监控（错误率/token 趋势）做统计意义上的质量判断

### Q2: "你们有 CI/CD 吗？每次 push 跑测试吗？"

**答**：目前没有 CI pipeline。测试是部署前手动跑 `pytest`。这是个人项目规模下的务实选择——但我会在 `.github/workflows/test.yml` 里写好了框架，后续接入 GitHub Actions 只需配 PostgreSQL service container。

### Q3: "你在这个项目里写过的最好的一个测试是哪个？"

**答**：`test_merge_skips_null_values` 和 `test_parse_malformed_json` 这两个。因为它们测的不是"正确输入→正确输出"，而是"LLM 的脏数据→系统不崩溃"。这类测试在传统项目中可能显得 paranoid，但在 LLM Agent 项目中，**LLM 返回异常格式是常态而非意外**。

### Q4: "AlfredAdmin（Go）为什么没写测试？"

**答**：AlfredAdmin 是新加的组件（2026-07-31），目前优先级是跑通功能链路（用户注册→JWT 签发→Python 验签→对话）。Go 的测试我会用标准库 `testing` + `httptest` 测 handler，`pgx` mock 或 testcontainers 测 store 层。结构上 handler→service→store 三层分离，每层接口清晰，加测试的改造成本很低。

---

## 八、关键 Commit 速查（面试引用用）

| Commit | 内容 | 可讲的点 |
|--------|------|---------|
| `3831e6a` | 取消 SSE，多 Agent 冲突 | 功能交互的边界问题 |
| `791bd28` | SQL `{}` 占位符冲突 | 跨系统边界的最隐蔽 bug |
| `ec44b2c` | nginx 子路径 HTML 修复 | 部署环境的边界测试 |
| `80d0e51` | lifespan 优雅降级 | 启动失败的边界处理 |
| `3d45a3d` | pgvector 扩展顺序修复 | 依赖初始化顺序问题 |
| `c6f1d3c` | rollback 前检查连接 | 资源清理的边界条件 |

---

> **总结一句话**：这个项目的测试哲学是 **"测死确定性逻辑，监控非确定性行为，用降级兜底代替崩溃"**。对于 LLM Agent 这种非确定性系统，传统的"输入→预期输出"模式只能覆盖 30%，剩余 70% 靠四条检测链路 + 日志驱动的问题发现。
