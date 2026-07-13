# 日志管理指南

> 如何阅读、管理和使用 MakeItSpecific 的日志

## 1. 日志架构

```
data/logs/
  app.log        ← 当前日志（5MB 滚动）
  app.log.1      ← 上一个（压缩归档）
  app.log.2      ← 再上一个
  app.log.3      ← 最老的一个（最多保留 3 个备份）
```

配置位置：`app.py` 顶部

```python
_file_handler = RotatingFileHandler(
    LOG_DIR / "app.log", maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8",
)
```

- 单文件最大 5MB
- 达到上限自动轮转，保留 3 个历史文件
- 同时输出到终端（stdout）和文件
- 编码 UTF-8

## 2. 日志格式

```
MM-DD HH:MM:SS [LEVEL] module | message
```

示例：
```
07-13 14:32:05 [INFO ] core.agent | [Memory] L2/L3 记忆系统已初始化
07-13 14:32:07 [INFO ] core.router | [Router] 意图: prompt_optimize ← "帮我写一个..."
07-13 14:32:12 [WARNING] core.graph | [Planner] LLM 失败，降级
07-13 14:32:15 [ERROR] core.graph | [Execute] ReAct Agent 失败: timeout
```

### Level 含义

| Level | 含义 | 要不要管 |
|-------|------|---------|
| `INFO` | 正常流程记录 | 了解系统运行的线索 |
| `WARNING` | 降级/跳过/可恢复 | 看一眼，可能表明配置问题 |
| `ERROR` | 调用失败/异常 | **必须**排查 |

## 3. 各模块的日志签名

| 模块 | 日志前缀 | 关键事件 |
|------|---------|---------|
| `core.agent` | `[Agent]` / `[Memory]` | Stream 失败、记忆初始化 |
| `core.graph` | `[Router]` / `[Planner]` / `[Execute]` / `[Checkpoint]` / `[Reflector]` | 意图判断、LLM 降级、ReAct 失败、语义偏移、质量不通过 |
| `core.context_engine` | `[ContextEngine]` | L2 摘要更新、L3 事实提取、话题切换 |
| `services.rag_service` | `[RAG]` | 索引、Rerank 失败 |
| `services.vector_store` | `[PGVector]` | 表创建、写入失败、检索失败 |
| `tools.*` | `[Tool]` | 工具调用、失败详情 |

## 4. 常用排查命令

### 4.1 看最近的错误

```bash
# 最近 30 条错误 + 警告
grep -E "\[ERROR\]|\[WARNING\]" data/logs/app.log | tail -30

# 只看 ERROR
grep "\[ERROR\]" data/logs/app.log | tail -20

# 搜索特定模块
grep "\[Execute\]" data/logs/app.log | tail -20
grep "\[RAG\]" data/logs/app.log | tail -20
```

### 4.2 追踪一次对话

```bash
# 找到对话开始时间，假定是 14:32
grep "07-13 14:3[2-9]" data/logs/app.log

# 更精确：找到 session_id 后追踪
grep "sess_20260713_143200_abc123" data/logs/app.log
```

### 4.3 性能诊断

```bash
# 看 Rerank 耗时
grep "Rerank" data/logs/app.log

# 看 Planner 降级频率（LLM 质量信号）
grep "降级" data/logs/app.log | wc -l

# 看 Reflector 不通过次数（输出质量信号）
grep "Reflector" data/logs/app.log | grep -v "LLM 失败"
```

### 4.4 知识库诊断

```bash
# 看索引了多少内容
grep "已索引" data/logs/app.log

# 看检索失败
grep "RAG.*失败\|检索失败" data/logs/app.log
```

## 5. 日志驱动的问题发现

### 5.1 高频信号 = 系统问题

| 信号 | 超过这个频率 | 说明 |
|------|------------|------|
| `Planner LLM 失败` | > 5% 的请求 | LLM 不可靠，检查 API / key |
| `Reflector 不通过` | > 20% 的请求 | 输出质量太差，检查 Prompt |
| `Checkpoint 语义偏移` | > 10% 的请求 | Planner 方向性指导不够 |
| `Rerank 失败` | 每次检索都失败 | API 配置问题 |
| `Embedding 失败` | 每次索引都失败 | DASHSCOPE_API_KEY 问题 |

### 5.2 沉默信号 = 可能的问题

- 日志里完全没有 `[Memory]` → 记忆系统未启用
- 日志里完全没有 `[RAG]` → 知识库未索引，需要 `POST /api/knowledge/reindex`
- 日志里完全没有 `[Checkpoint]` → 正常（意味着没有偏移）
- 日志里完全没有 `[Tool]` → Executor 没有用工具，可能效果不好

## 6. 日志存储管理

### 6.1 当前配置

- 单文件 5MB × 4 个（当前 + 3 备份）= 最多 20MB
- 对于个人使用完全够
- 如果要保留更久的历史，开大 `backupCount` 或改用外部日志系统

### 6.2 手动清理

```bash
# 删除所有旧日志
rm data/logs/app.log.*

# 删除所有日志（下次启动重建）
rm -rf data/logs/

# 清空当前日志
> data/logs/app.log
```

### 6.3 升级考虑

如果未来需要更专业的日志管理，可以：
1. 接入 Loki + Grafana（适合容器环境）
2. 用 `logging.handlers.TimedRotatingFileHandler` 按天轮转
3. 加结构化日志（JSON 格式），方便脚本解析

## 7. Docker 环境

Docker 容器中日志同样输出到 `data/logs/app.log`，该目录通过 volume 持久化：

```yaml
volumes:
  - specificdata:/app/data
```

查看容器内日志：
```bash
docker exec -it specific-api cat /app/data/logs/app.log
docker exec -it specific-api tail -100 /app/data/logs/app.log
```
