# MakeItSmooth 项目治理

> 项目宪章 — Agent 开发、审查、上线的流程规范。
> 每次修改 Agent 行为前，查阅此文件。

---

## 一、Agent 开发原则

### 1.1 ReAct 范式强制

- Agent **必须**使用 ReAct (Reasoning + Acting) 范式
- **禁止**硬编码 if-else 决策链路
- 每个决策点（路由、追问、重试）必须经过 LLM 推理节点
- 例外：安全规则、速率限制、危险操作拦截（这些可以用规则，不动 LLM）

### 1.2 Tool 调用规范

- 每个 Tool 必须有清晰的 `description`（Agent 据此决定何时调用）
- Tool 必须有超时（默认 30s，可配置）
- Tool 失败不抛异常，返回错误描述文本，让 Agent 自行处理
- Tool 调用记录必须可追踪（输入/输出/耗时/token）

### 1.3 大模型无关

- Provider 切换不能影响 Agent 行为
- System Prompt 中不写任何 provider 专属的指令
- 不在 Prompt 中 hardcode 模型名

---

## 二、代码审查 Checklist

在合并 Agent 行为相关 PR 前，检查：

```
[ ] 1. 是否新增/修改了 System Prompt？
        → 必须附 before/after 对比 + 3 个测试用例的结果对比

[ ] 2. 是否新增了 Tool？
        → 必须附 Tool 描述 + 安全审查（是否有文件写/网络/系统访问）
        → 必须附 Agent 调用该 Tool 的一个完整 trace

[ ] 3. 是否修改了 Graph 拓扑（节点/边/条件路由）？
        → 必须画 ASCII 图（新拓扑）
        → 必须标注每个节点的输入/输出 schema

[ ] 4. 是否涉及幻觉风险？
        → 如果 Agent 有生成「事实性断言」的新能力 → 必须附幻觉检测策略

[ ] 5. 是否变更了 LLM Provider 配置？
        → 必须测试至少 2 个 Provider（如 DashScope + DeepSeek）

[ ] 6. 是否涉及用户数据存储？
        → 必须标注存储位置、保留期限、可删除性

[ ] 7. 是否新增了依赖？
        → 必须说明为什么不能用现有依赖替代
```

---

## 三、安全规范

### 3.1 沙箱安全

- `python_exec` Tool 默认关闭（`SANDBOX_ENABLED=false`）
- 启用前必须审查禁止列表：文件写、网络、subprocess、os.system、eval/exec
- 生产环境建议用 Docker 沙箱（gVisor/Firecracker），不直接 exec

### 3.2 输入安全

- 所有用户输入必须经过 HTML 转义后再渲染到 WebUI
- API 端点必须有输入长度限制（message ≤ 10000 字符）
- URL 输入（fetch_url）必须验证协议（仅 http/https）

### 3.3 输出安全

- Agent 输出中如果包含可执行代码，必须标注 "⚠️ 请勿直接执行"
- Agent 生成的 shell 命令必须在 WebUI 显示为代码块（不可点击执行）
- Agent 禁止输出系统路径、API Key、私密配置（用正则后处理检查）

### 3.4 API Key 管理

- 所有密钥从环境变量读取，**禁止**硬编码
- 日志输出中脱敏 API Key（`sk-***...***xyz`）
- 前端不暴露任何 API Key

---

## 四、Agent 质量指标

### 4.1 核心指标

| 指标 | 目标 | 说明 |
|------|------|------|
| 任务完成率 | ≥ 85% | 用户没有在 2 轮内放弃或手动重试 |
| 幻觉率 | ≤ 10% | 输出中可以被验证的声明中，有多少被证伪 |
| 平均 tool call 轮数 | 2-5 | <2 说明工具没用上，>5 说明循环风险 |
| Planner 准确率 | ≥ 80% | is_complete 判断与实际用户需求的吻合度 |
| 追问效率 | 每轮减少 ≥2 个缺口 | 追问后信息缺口显著减少 |

### 4.2 监控方式

- LangFuse 追踪每次 Agent 运行（token、延迟、tool call 链）
- 每 100 次对话抽 10 条人工审查
- 月报：任务完成率趋势 + 幻觉率趋势

---

## 五、模型降级策略

```
优先级: 用户指定模型 > LLM_PROVIDER 配置 > auto 检测

降级链（auto 模式）:
  1. 首个有 API Key 的 provider
  2. 如果调用失败（超时/余额不足/限流）
     → 自动降级到下一个有 Key 的 provider
     → 降级时通知用户："主模型暂时不可用，已切换到 XX"

补充规则:
  - 追问阶段用便宜模型 (qwen-turbo / deepseek-chat)
  - 执行阶段用强模型 (qwen-plus / gpt-4o)
  - Reflector 评分用小模型 (节省 token)
```

---

## 六、多 Agent 协作协议（将来）

> 当单 Agent 无法完成任务时，主 Agent 可以 spawn 子 Agent

```
主 Agent (Orchestrator)
  │
  ├── 子 Agent 1: Researcher     — search_web + fetch_url → 调研报告
  ├── 子 Agent 2: Coder          — python_exec + search_kb → 代码/分析
  ├── 子 Agent 3: Reviewer       — 审查子 Agent 产出 → 质量报告
  └── 子 Agent 4: Writer          — 汇总所有产出 → 最终文档

通信协议:
  - 主 Agent → 子 Agent: 任务描述 + 输入上下文
  - 子 Agent → 主 Agent: 结构化结果 + 置信度 + 引用来源
  
  - 超时: 子 Agent 30s 无响应 → 主 Agent 放弃该子任务
  - 冲突: 两个子 Agent 结论矛盾 → Reviewer 裁决
```

---

## 七、项目文件规范

```
MakeItSmooth/
├── GOVERNANCE.md       ← 本文件（项目治理章程）
├── CLAUDE.md           ← 开发者文档（架构/启动/开发指南）
├── CAPABILITIES.md     ← 能力清单（Tools / Skills / MCP / API Key 矩阵）
├── TODO.md             ← 待做事项
├── README.md           ← 用户文档
├── CHANGELOG.md        ← 版本变更记录（将来）
│
├── .env.example        ← 环境变量模板
├── .gitignore
│
├── core/               ← Agent 核心引擎（不动 SKILL 代码）
├── skills/             ← Skill 定义（业务逻辑）
├── tools/              ← Tool 定义（原子能力）
├── memory/             ← 记忆系统
├── services/           ← 基础设施（DB / RAG / 导出）
├── routers/            ← API 路由
├── prompts/            ← 所有 Prompt 模板
└── tests/              ← 测试
```

**修改规则**:
- `core/` 里的改动需要代码审查（影响 Agent 行为）
- `skills/` 可以直接改（业务逻辑，单独测试）
- `prompts/` 改动必须附 before/after 对比
- `tools/` 新增必须附安全审查
