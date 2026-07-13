# Token 监管指南

> Token 是 AI Agent 的货币 — 花多少、花在哪、花得值不值

## 1. Token 是什么

LLM 不是按字符/字数计费，而是按 **token**。一个 token 约等于：

| 语言 | 1 token ≈ |
|------|----------|
| 英文 | 0.75 个单词 / 4 个字符 |
| 中文 | 1-2 个汉字 |
| 代码 | 1-3 个字符（符号密集时更费） |

粗略换算：**1K tokens ≈ 750 英文单词 ≈ 500-700 个中文字**

## 2. MakeItSpecific 的 Token 流向

一次用户对话中，Token 被消耗在以下节点。不是每个节点每轮都触发：

```
用户消息
  │
  ▼
Router (LLM 意图分类)                    ← input: ~100 | output: ~5
  │                                        仅在 module=auto 时触发
  ▼
Planner (LLM 需求分析 + 维度提取)         ← input: ~1500-4000 | output: ~200
  │                                        每轮都触发
  │
  ├─→ Clarify (追问模板, 非 LLM)          ← 零 Token
  │
  └─→ Execute (ReAct Agent Loop)
        │
        ├─ Think (内部)                   ← output token (流式推送)
        ├─ Act (Tool Call)                ← 工具调用本身不消耗 LLM Token
        │    ├─ search_knowledge_base     但工具返回会作为下一轮 Think 的 input
        │    ├─ python_exec
        │    ├─ run_shell_preview
        │    └─ add_to_knowledge_base
        └─ Observe (工具结果 → input)      ← 追加到上下文

  ├─→ Checkpoint (语义校准)               ← input: ~500 | output: ~100
  │                                        仅 Executor 完成 + checkpoint_retry < 1 时触发
  │
  └─→ Reflector (质量审核)                ← input: ~500 | output: ~100
                                           仅 score < 7 时可能触发 retry (最多2次)

每轮对话后 (ContextEngine):
  L2 摘要更新                              ← input: ~500 | output: ~150
  L3 事实提取                              ← input: ~500 | output: ~100

会话完成时 (Memory):
  L2 会话摘要                              ← input: ~2000 | output: ~200
  L3 画像更新                              ← input: ~1000 | output: ~100
```

### 单轮对话的 Token 模型

| 场景 | 典型 Token 消耗 |
|------|----------------|
| 简单追问（信息不够，Clarify） | Planner(input) ~2000 + Planner(output) ~150 = **~2150** |
| 正常执行（无工具调用） | Planner(~2000) + Executor Think(~500+300 out) + Checkpoint(~500+100) + Reflector(~500+100) = **~4000** |
| 复杂执行（3 轮工具调用） | Planner(~3000) + Executor ×3(~800+400 per round) + Checkpoint + Reflector = **~7500** |
| 带 RAG（知识库命中） | 上述 + RAG 上下文(~1000) = **+1000** |
| Reflector 重试 1 次 | 上述 + Execute(第二轮) + Reflector(第二轮) = **+3000-5000** |
| L2 摘要更新 | +~650 |
| L3 事实提取 | +~600 |
| L2+L3 Memory (会话完成时) | +~3300 |

---

## 3. 怎么数 Token

### 3.1 Python 脚本（离线估算）

```python
import tiktoken

# OpenAI 兼容模型的 tokenizer
enc = tiktoken.get_encoding("cl100k_base")  # GPT-4 / DeepSeek

text = "你的 prompt 文本"
tokens = enc.encode(text)
print(f"Token 数: {len(tokens)}")
print(f"字符数: {len(text)} → 压缩比: {len(text)/len(tokens):.1f} 字符/token")
```

DeepSeek / Qwen / OpenAI 都使用 `cl100k_base` 编码（或兼容变体），误差在 5% 以内。

### 3.2 API Response Header（实时监控）

```python
# 在 llm_client.py 或 Agent 调用后读取
response = await model.ainvoke(messages)
# DashScope / OpenAI 兼容格式:
usage = response.response_metadata.get("token_usage", {})
input_tokens = usage.get("prompt_tokens", 0)
output_tokens = usage.get("completion_tokens", 0)
print(f"本次: input={input_tokens} output={output_tokens} total={input_tokens+output_tokens}")
```

### 3.3 LangSmith / LangFuse（外部追踪）

```bash
# 启用 LangSmith 追踪（需 API Key）
export LANGCHAIN_TRACING_V2=true
export LANGCHAIN_API_KEY=ls__xxx
export LANGCHAIN_PROJECT=makeitspecific
```

所有 LangChain 调用自动上报，可以在 Web UI 看到每步的 Token 消耗。

---

## 4. 流式 Token 追踪

### 4.1 前端侧（已实现）

`static/js/chat.js` 的 `handleSSEEvent` 在收到 `token` 事件时累加 `token_count`，最后在 `done` 事件中接收完整的 `tokens_used`：

```javascript
case 'done':
  // data.tokens_used = 本次对话的总输出 token 数
```

### 4.2 后端侧日志监控

在 `data/logs/app.log` 中提取 Token 信息：

```bash
# 查看 token 相关日志
grep -i "token\|usage\|tokens_used" data/logs/app.log

# 目前前端 done 事件含 tokens_used，后端可以加以下日志：
# [Agent] Stream 完成: session=sess_xxx tokens=1234 rounds=3
```

### 4.3 建议加的后端埋点

在 `core/agent.py` 的 `process_message_stream` 的 done yield 之前加一行日志：

```python
logger.info(f"[Agent] done session={session_id} tokens={token_count} intent={intent.get('label','?')}")
```

这样每次对话完成都在日志留下 Token 足迹。

---

## 5. 上下文窗口管理

### 5.1 各模型的上下文窗口

| 模型 | 最大上下文 |
|------|-----------|
| Qwen-Plus | 131K tokens |
| Qwen-Turbo | 1M tokens |
| DeepSeek-Chat (V3) | 64K tokens |
| DeepSeek-R1 | 64K tokens |
| GPT-4o | 128K tokens |
| GPT-4o-mini | 128K tokens |

### 5.2 MakeItSpecific 的上下文构成

每轮 Executor 的输入由以下部分拼接：

```
System Prompt (固定)
  EXECUTOR_SYSTEM_PROMPT           ~800 tokens
  Skill System Prompt              ~600 tokens
  ─────────────────────────────────────
  L1 最近 3 轮原文                 ~2000 tokens (每轮 ~700)
  L2 滚动摘要                      ~300 tokens (压缩版，控制在 256 内)
  L3 语义事实                      ~200 tokens
  Checkpoint 反馈                  ~100 tokens (如有)
  RAG 检索结果                     ~500-1500 tokens (取决于命中)
  用户原始消息 + 已确认维度         ~500 tokens
  Plan (goal + steps)              ~100 tokens
  ─────────────────────────────────────
  总计（不含历史）                  ~3100-5100 tokens
  总计（含 L1 3 轮历史）           ~5100-7100 tokens
```

### 5.3 什么时候会爆窗口

```
ReAct 循环 ×10 轮 × (工具输入 300 + 工具输出 800) = 11,000 tokens 追加
+ 基础上下文 ~6000 tokens
+ Checkpoint + Reflector ~1500 tokens
= ~18,500 tokens (一个复杂对话)
```

对于 64K 窗口完全够。即使 10 轮工具调用 + 两轮对话 + L2 摘要更新，也很难超过 30K。

**但要注意**：`search_knowledge_base` 返回的 RAG 结果可能很长（最多 ~1500 tokens），如果 Executor 重复调用同一个 query，旧结果和旧对话一起堆积在上下文中。

### 5.4 防护措施

| 层级 | 机制 | 位置 |
|------|------|------|
| L1 | 只保留最近 3 轮 | `context_engine.py` `L1_MAX_TURNS=3` |
| L2 | 滚动摘要控制在 256 tokens | `DEFAULT_MAX_SUMMARY_TOKENS=256` |
| Executor | 最多 10 轮 tool call | `config.py` `max_tool_rounds=10` |
| RAG | 只返回 top 3 | `search_knowledge_base` `top_k=3` |
| RAG | 相似度阈值过滤 | `config.py` `similarity_threshold=0.6` |

---

## 6. Token 成本估算

### 6.1 各 Provider 价格（2026-07）

| Provider | 模型 | Input (每 1M tokens) | Output (每 1M tokens) |
|----------|------|---------------------|----------------------|
| DashScope | qwen-plus | ¥2 | ¥6 |
| DashScope | qwen-turbo | ¥0.3 | ¥0.6 |
| DeepSeek | deepseek-chat | ¥1 | ¥2 |
| DeepSeek | deepseek-reasoner | ¥4 | ¥16 |
| OpenAI | gpt-4o | $2.50 | $10.00 |
| OpenAI | gpt-4o-mini | $0.15 | $0.60 |
| DashScope | text-embedding-v4 | ¥0.0005/1K tokens | — |
| DashScope | qwen3-rerank | ¥0.003/1K tokens | — |

### 6.2 单次对话成本估算

以 **deepseek-chat** 为例，一次完整对话（执行 + 无工具调用）：

```
Input:  5000 tokens × ¥1/1M  = ¥0.005
Output: 800 tokens × ¥2/1M   = ¥0.0016
─────────────────────────────────────────
LLM 调用:                     ≈ ¥0.0066

Embedding (RAG): 1K tokens × ¥0.0005/1K = ¥0.0005
Rerank:          5 docs × ¥0.003/1K × 1K = ¥0.003
─────────────────────────────────────────
总计:                         ≈ ¥0.01
```

一天 100 次对话 ≈ **¥1.00**，一个月 ≈ **¥30**。

如果用 **qwen-turbo**：一天 100 次 ≈ **¥0.30**，一个月 ≈ **¥9**。

### 6.3 隐藏成本

| 来源 | 成本比例 | 说明 |
|------|---------|------|
| Reflector 重试 | 额外 +50-100% | score < 7 触发，最多 2 次 |
| Checkpoint 偏移重试 | 额外 +50% | 语义未对齐，回 execute |
| L2 摘要 + L3 提取 | 每轮 +10% | 每轮对话后都触发 |
| L2+L3 Memory | 会话完成时 +5-10% | 只写一次，非每轮 |

如果 Reflector 频繁 retry（说明输出质量差），Token 成本翻倍。这是值得盯的信号。

---

## 7. 信号 — 该看什么

### 7.1 健康信号

| 信号 | 含义 |
|------|------|
| 每轮 `token_count` 在 300-800 | 正常输出长度 |
| Reflector score 持续 ≥ 7 | 不需要重试，没有浪费 |
| RAG 每次命中且有来源标注 | 知识库有效 |
| Planner 没有降级 | LLM 稳定 |

### 7.2 异常信号

| 信号 | 含义 | 排查 |
|------|------|------|
| `token_count` 突然 > 2000 | 输出过长，可能在重复或堆叠内容 | 看那轮的对话内容 |
| Reflector score 连续 < 7 | 输出质量差，触发重试，Token 浪费 | 检查 System Prompt 和模型配置 |
| Planner 频繁降级 | LLM API 不稳定 or 模型质量下降 | 检查 API key 和 network |
| L2 摘要每轮增长 | 对话在跑题，一直在聊新东西，没有收敛 | 检查 Router 和 Planner 的意图判断 |
| RAG 检索结果为空 | 知识库缺失 or query 太模糊 | 补知识库 or 改进 query 增强 |
| Executor 工具调用 < 1 次 | Agent 没用工具就给出了答案 | 可能是简单问题（正常），也可能是不会用工具（prompt 问题） |

### 7.3 Token 消耗趋势监控命令

```bash
# 粗略估算最近日志的 Token 消耗（统计 done 事件）
grep "tokens_used" data/logs/app.log | \
  awk -F'tokens_used' '{print $2}' | \
  awk -F',' '{sum+=$1; count++} END {print "avg token/msg:", sum/count, "| total msgs:", count}'

# 看最近 Token 最高的 10 条
grep "tokens_used" data/logs/app.log | sort -t: -k2 -rn | head -10
```

---

## 8. 怎么省 Token

### 8.1 已经做的

- ✅ L1 只保留最近 3 轮（`L1_MAX_TURNS=3`）
- ✅ L2 滚动摘要压缩全量历史（`max_summary_tokens=256`）
- ✅ RAG 只返回 top 3，rerank 前 coarse_k=20
- ✅ Executor 10 轮上限，防止死循环
- ✅ Checkpoint 最多重试 1 次，Reflector 最多 2 次
- ✅ 长 query (>80 字符) 不增强，保护原始语义

### 8.2 可以进一步做的

| 手段 | 效果 | 代价 |
|------|------|------|
| **RAG 结果压缩** — 检索到的 chunk 超过 500 字符时截断 | 减少 Executor input 的 20-30% | 可能丢失细节 |
| **Planner 只在首轮调用** — 多轮追问后不再重新分析 | 节省每轮 ~2000 tokens | 可能错过用户新说的信息 |
| **Reflector 默认关闭** — 只在用户点 👎 后触发深度检查 | 节省每轮 ~600 tokens | 输出质量无保障 |
| **qwen-turbo 做轻量节点** — Router/Checkpoint/Reflector 用便宜模型 | 这 3 个节点成本降低 80% | 分类/审核精度可能下降 |
| **System Prompt 精简** — 当前 EXECUTOR 约 800 tokens，压缩到 400 | 节省每轮 ~400 tokens | Prompt 工程量大 |

---

## 9. 实用工具

### 9.1 手工审计一次对话的 Token

```python
# save as check_tokens.py, run with: python check_tokens.py sess_xxx
import json, tiktoken

enc = tiktoken.get_encoding("cl100k_base")

# 从 DB / 日志中拉取某次对话的输入输出
conversation = [...]  # list of {role, content}

total_input = 0
total_output = 0

for msg in conversation:
    tokens = len(enc.encode(msg["content"]))
    if msg["role"] == "user":
        pass  # User messages don't count as LLM cost
    elif msg["role"] == "assistant":
        total_output += tokens
    # System prompt and injected context also count
    total_input += tokens

print(f"估算 input:  {total_input} tokens")
print(f"估算 output: {total_output} tokens")
print(f"估算 DeepSeek 成本: ¥{(total_input/1e6)*1 + (total_output/1e6)*2:.4f}")
```

### 9.2 Curl 看 SSE Token 流

```bash
curl -N -X POST "http://localhost:8001/api/chat/stream?v=2" \
  -H "Content-Type: application/json" \
  -d '{"message":"帮我审查 main.py","module":"code_review"}' \
  2>&1 | while IFS= read -r line; do
    if [[ "$line" == data:* ]]; then
      echo "$line" | cut -c6- | python -m json.tool 2>/dev/null
    fi
  done
```

关注 `event: done` 里的 `tokens_used`。

---

## 10. 总结

| 层级 | 做什么 | 怎么看 |
|------|--------|--------|
| **日常** | 看日志里的 done 事件 token 数，盯异常值 | `grep "done" data/logs/app.log` |
| **每周** | 算平均 Token/对话，看趋势有没有上涨 | 参考第 7.3 节的 awk 命令 |
| **每月** | 按 Provider 算实际花费，和预估对比 | 看 API 控制台的 billing |
| **异常时** | 对高 Token 会话做手工审计，定位浪费源 | 参考第 9.1 节的 Python 脚本 |
