# 任务契约 (TaskContract) — 设计教程

> 把用户模糊的想法，整理成其他 Agent 可以可靠执行的「合同」

---

## 目录

1. [一句话说清](#1-一句话说清)
2. [为什么需要任务契约](#2-为什么需要任务契约)
3. [契约的 7 个字段](#3-契约的-7-个字段)
4. [完整示例：看一条模糊需求如何变成契约](#4-完整示例看一条模糊需求如何变成契约)
5. [契约的生成流程](#5-契约的生成流程)
6. [何时确认、何时放过](#6-何时确认何时放过)
7. [契约作为后续节点的唯一真相源](#7-契约作为后续节点的唯一真相源)
8. [数据结构设计](#8-数据结构设计)
9. [技术实现路线](#9-技术实现路线)
10. [常见反模式](#10-常见反模式)

---

## 1. 一句话说清

> **任务契约 = 在 Agent 动手之前，先签一份轻量的「工作约定」——明确要做什么、做到什么程度、什么不能碰。**

它不是需求文档，不是 PRD，而是一份经过用户确认的**可执行任务说明书**。长度通常在 200–400 字，够准确但不冗长。

---

## 2. 为什么需要任务契约

### 2.1 当前的痛点

Alfred 现在的流程是：

```
用户: "帮我写个用户登录系统"
  → Planner: LLM 提取维度 → completeness 评分
  → Clarify: 生成几个追问（"用什么框架？""数据库？""要不要OAuth？"）
  → 用户回答完 → Execute 开始干活
```

这个流程的问题是**信息分散**：

| 问题 | 现状 |
|------|------|
| Planner 提取的维度存在哪？ | `expressed_dimensions` dict，散在各处 |
| 追问完的确认在哪？ | 隐式存在对话里，靠 L2 摘要勉强记住 |
| Execute 怎么知道边界？ | 靠 prompt 里的 `expressed_dimensions` 文本拼接 |
| 做完后怎么验证是否满足了最初要求？ | Reflector 和 Checkpoint 各做一次，但依据不在一个统一的地方 |
| 下次继续这个任务时还记不记得？ | 如果跨了会话，基本靠 L3 事实碰运气 |

**没有一个结构化的「任务定义」贯串全链路。**

### 2.2 契约的价值

```
没有契约                                  有契约
────────────────────────────────────  ────────────────────────────────────
Planner → 散装维度 dict               Planner → 写入 TaskContract
Executor → 靠 prompt 拼凑理解          Executor → 读取 TaskContract 作为
要点                                      System Prompt 的核心组成部分
Reflector → 自己猜测"用户想要什么"     Reflector → 逐字段对照契约检查
跨会话 → L3 碎片回忆                 跨会话 → 加载上次契约，2 秒恢复状态
用户想改方向 → 不知道改了什么         用户想改 → 修改契约某一字段，增量更新
```

一句话：**契约是全链路共享的「唯一真相源」（Single Source of Truth）。**

---

## 3. 契约的 7 个字段

```
TaskContract
├── goal             最终目标     — 一句话，用户真正要完成什么
├── scope            工作范围     — 要做什么 / 不要做什么
├── constraints      约束         — 技术/业务/时间上的硬限制
├── acceptance       验收标准     — 做到了什么算完成
├── risks            风险边界     — 什么情况下停下来问，不要自己决定
├── permissions      执行权限     — 允许读什么、写什么、调什么 API
└── deliverables     期望交付物   — 最终输出什么格式 / 什么产物
```

### 3.1 `goal` — 最终目标

**一句话，用户真正要完成什么。**

不要写「实现登录功能」，要写「为个人博客项目添加用户名+密码登录，月底上线用」。

规则：
- 必须是用户的视角，不是技术的视角
- 不超过一句话（50 字以内）
- 如果用户的目标本身还模糊 → 写在 goal 里，标记 `confidence: low`，后续追问收敛

### 3.2 `scope` — 工作范围

**要做什么 + 不要做什么，两个都要明确。**

```
scope:
  in:  ["用户名+密码注册", "登录态保持 (session)", "登录/注册页面 UI"]
  out: ["OAuth 第三方登录", "密码找回", "邮箱验证", "权限管理"]
```

规则：
- `out` 比 `in` 更重要——限制边界是防 Agent 跑偏的关键
- 如果用户没说清楚边界，追问优先收敛 out（"要不要也做 OAuth？" 比 "用什么 UI 库？" 重要）
- 允许留空，但 `out` 为空意味着 Agent 权限很大，permissions 必须收紧

### 3.3 `constraints` — 约束

**技术上、业务上、时间上不能突破的硬限制。**

```
constraints:
  - 必须用 React + TypeScript（技术约束）
  - 后端用已有的 FastAPI 框架，不新增后端服务（技术约束）
  - 下周五之前必须上线（时间约束）
  - 密码至少 8 位，必须含字母和数字（业务约束）
  - 不得引入超过 2 个新 npm 依赖（技术约束）
```

规则：
- 只放「不能突破」的硬限制，软偏好放 preference 字段（心智模型里）
- 区分「约束」和「偏好」：约束是红线，偏好是加分项
  - 约束：「不得用 Redux」→ 用了就是失败
  - 偏好：「偏好轻量方案」→ 用了 Redux 不算失败，但不够好

### 3.4 `acceptance` — 验收标准

**做到什么程度算「完成」，可验证的具体条件。**

```
acceptance:
  - 用户可以用邮箱+密码注册新账号
  - 已登录用户在 session 有效期内不需要重复登录
  - 登录/注册页面在移动端和桌面端均正常显示
  - 密码错误时有明确提示，不暴露具体是用户名不对还是密码不对
```

规则：
- 每一条必须是**可验证的**行为描述，不是技术实现描述
- 避免：「实现了 bcrypt 加密」→ 不可验证
- 改成：「密码以不可逆形式存储，数据库泄露时无法还原原文」
- 如果用户提不出验收标准 → 追问："这个功能做到什么程度你觉得可以上线？"

### 3.5 `risks` — 风险边界

**什么情况下 Agent 应该停下来问，而不是自己决定。**

```
risks:
  - 涉及密码存储：加密方案必须用户确认
  - 涉及数据库 schema 变更：必须先展示 diff 再执行
  - 外部 API 调用失败时：继续还是暂停，需确认
  - 如果建议的新依赖有安全漏洞警告 → 暂停
```

规则：
- 这是 L2/L3 自主决策分级的核心输入
- risks 里写的 → 自动决策时跳过，必须人工确认
- risks 为空 → Agent 默认策略：改代码可以，删数据/改基础设施必须问

### 3.6 `permissions` — 执行权限

**Agent 被允许做什么操作。**

```
permissions:
  read:  ["src/**/*.tsx", "src/**/*.ts", "package.json", "tsconfig.json"]
  write: ["src/components/Login.tsx", "src/components/Register.tsx", "src/utils/auth.ts"]
  execute: ["npm test", "npm run lint"]
  api:    []          # 不允许调外部 API
  shell:  ["npm *"]   # 允许 npm 相关命令
```

规则：
- 初期版本可以简化：`read: all, write: ask, execute: ask`
- 写权限默认是「需要确认」，除非用户在契约中明确放开
- permissions 是安全兜底，不是信任判断——即使 Agent 道德高尚，契约也必须有边界

### 3.7 `deliverables` — 期望交付物

**最终输出什么格式、什么产物。**

```
deliverables:
  format: "代码改动 + PR 描述"
  artifacts:
    - Login.tsx 组件
    - Register.tsx 组件
    - auth.ts 工具模块
    - 单元测试文件（至少覆盖正常登录和密码错误两个场景）
    - PR 描述（含功能说明、截图、测试结果）
```

规则：
- 和 acceptance 互补：acceptance 说「功能上做到什么」，deliverables 说「物理上交付什么」
- 明确格式（markdown / 代码 / PR / 部署链接 / 截图）
- 如果 deliverable 是一个 PR，接受标准可以写了「PR 通过 CI + 至少 1 人 approve」

---

## 4. 完整示例：看一条模糊需求如何变成契约

### 4.1 用户输入（模糊）

> "帮我给我那个博客项目加个登录功能"

### 4.2 Planner 第一轮分析

Alfred 分析当前项目上下文（已知：React + FastAPI 博客项目，已有基础路由），输出初始契约草案：

```json
{
  "goal": "为现有 React+FastAPI 博客项目添加用户登录功能",
  "confidence": 0.4,
  "scope": {
    "in": ["用户登录", "会话保持"],
    "out": []
  },
  "constraints": [
    "前端 React + TypeScript（已知）",
    "后端 FastAPI（已知）"
  ],
  "acceptance": [],
  "risks": ["涉及密码存储"],
  "permissions": {
    "read": "project",
    "write": "ask",
    "execute": "ask"
  },
  "deliverables": {
    "format": "代码改动",
    "artifacts": []
  }
}
```

`confidence: 0.4` → 低于 0.75 阈值 → 触发 Clarify。

### 4.3 Clarify 追问

Alfred 不把所有缺失字段逐一追问，而是**按风险优先级挑最重要的 3 个**：

> 好的，加登录功能。我有几个关键问题确认一下：
>
> 1. **范围**：要不要同时做注册功能？还是只有已有账号的登录？（这决定工作量差一倍）
> 2. **登录方式**：用户名+密码就够了，还是需要邮箱注册、OAuth（Google/GitHub）？
> 3. **安全要求**：密码存储和 session 管理有特定要求吗？还是我用 bcrypt + JWT 这种标准方案就行？

### 4.4 用户回答后 → 确认契约

```json
{
  "goal": "为现有 React+FastAPI 博客项目添加用户名+密码登录+注册功能",
  "confidence": 0.9,
  "scope": {
    "in": [
      "用户名+密码注册（含前端表单+后端API）",
      "用户名+密码登录",
      "登录态保持（JWT token + 7天过期）",
      "前端登录/注册页面 + 路由"
    ],
    "out": [
      "OAuth 第三方登录",
      "邮箱验证",
      "密码找回/重置",
      "权限管理（所有用户同等权限）"
    ]
  },
  "constraints": [
    "前端 React + TypeScript，不新增路由库（用已有 react-router）",
    "后端 FastAPI，密码存储用 bcrypt",
    "JWT token 有效期 7 天",
    "不得新增超过 2 个 npm 依赖",
    "UI 风格与现有博客页面一致（黑金主题）",
    "下周五之前完成"
  ],
  "acceptance": [
    "新用户可注册账号（用户名+密码），注册后自动登录",
    "已注册用户可用用户名+密码登录",
    "7 天内返回页面无需重新登录",
    "密码错误时提示「用户名或密码错误」不区分具体原因",
    "登录/注册页面在移动端和桌面端均正常显示",
    "现有博客功能（文章列表/详情）不受影响"
  ],
  "risks": [
    "密码存储方案必须用户确认（bcrypt 参数）",
    "数据库新增 users 表 → 先展示 DDL diff 再执行",
    "涉及现有 API 路由的修改 → 必须先列影响范围"
  ],
  "permissions": {
    "read": "project",
    "write": "src/components/*, src/pages/*, src/utils/*, backend/app/routers/*, backend/app/models/*",
    "execute": "npm test, npm run lint, pytest",
    "api": [],
    "shell": "npm *, pip *, pytest"
  },
  "deliverables": {
    "format": "代码改动 + PR",
    "artifacts": [
      "Login.tsx / Register.tsx 页面组件",
      "auth.ts 工具模块（token 管理）",
      "后端 /api/auth/login, /api/auth/register 接口",
      "users 表 DDL",
      "单元测试：登录成功、密码错误、注册重复用户名",
      "PR 描述（含功能说明 + 截图 + 测试结果）"
    ]
  }
}
```

**这时才交给 Execute。Agent 手里有明确的边界和标准，跑偏的概率大大降低。**

---

## 5. 契约的生成流程

```
用户输入
    │
    ▼
┌─────────────────────────────────────────────────────┐
│ Planner (升级版)                                     │
│                                                      │
│ 输入: 用户消息 + L1/L2/L3 记忆 + 项目上下文 + 能力卡片│
│                                                      │
│ 输出:                                                │
│   TaskContract (初始草案)                             │
│   + confidence (0-1)                                 │
│   + missing_fields (哪些字段信息不足)                  │
│   + clarify_questions (按优先级排序，最多 3 个)        │
│                                                      │
│ 策略:                                                │
│   - 已知信息直接填入对应字段                          │
│   - 信息不足的字段标记 missing                        │
│   - 如果已有上次契约 → 增量更新而非全量重建            │
└──────────────────────┬──────────────────────────────┘
                       │
              ┌────────┴────────┐
              │                 │
         confidence < 0.75     confidence ≥ 0.75
              │                 │
              ▼                 ▼
        ┌──────────┐    ┌──────────────┐
        │ Clarify  │    │ 展示契约卡片  │
        │ 追问收敛 │    │ 用户确认/修改 │
        │          │    │              │
        │ 缺什么问  │    │ 确认后 →     │
        │ 什么      │    │ Execute      │
        └────┬─────┘    └──────┬───────┘
             │                 │
             ▼                 │
        用户回答                │
             │                 │
             └────→ Planner ──┘
             (循环，最多 3 轮)
```

### 5.1 关键设计决策

**Q: 为什么是 0.75 阈值？**

7 个核心字段中，goal + scope 至少各占 30% 权重。如果 goal 模糊或 scope 边界缺失，confidence 必然低于 0.75。这个阈值是实验性的——太低了 Agent 会放任模糊任务通过，太高了会频繁追问惹恼用户。

**Q: 追问怎么排优先级？**

```
追问优先级 = 风险等级 × 信息缺口影响面

风险等级:
  高 (= 3): 涉及安全、数据、基础设施
  中 (= 2): 涉及架构、技术选型
  低 (= 1): 涉及 UI、文案、格式

信息缺口影响面 = 缺了这个信息，后续工作有多少比例需要返工
  - scope 缺失 → 0.8 (可能导致做错整个功能)
  - acceptance 缺失 → 0.3 (可以做，但验收不了)
  - 代码风格偏好 → 0.1 (不太影响返工)
```

### 5.2 增量更新

用户说「换方向」「改成……」时，不是丢弃整个契约重建，而是：

```
当前契约                        用户说 "不用 JWT 了，改用 session+cookie"
    │                                      │
    ├─ goal: ...                           ▼
    ├─ scope: ...               ┌────────────────────┐
    ├─ constraints:             │ 只更新受影响的字段:  │
    │    - JWT token 7天        │   constraints:      │
    ├─ ...                      │     ~~JWT 7天~~     │
                                │     + session+cookie│
                                │   risks:            │
                                │     + CSRF 防护确认 │
                                │   acceptance 微调   │
                                └────────────────────┘
```

规则：
- 只更新受影响的字段，不影响的部分保持不动
- 增加 `updated_at` 和 `version` 字段
- 旧版本保留在 `contract_history`（方便回溯）

---

## 6. 何时确认、何时放过

不是每次对话都需要契约。契约有成本（追问成本 + 等待用户确认的时间成本），需要用对场景。

| 场景 | 是否需要契约 | 说明 |
|------|------------|------|
| 「帮我写个登录系统」 | ✅ 完整契约 | 新任务，范围大，有安全风险 |
| 「登录页面的按钮改成金色」 | ❌ 不需要 | 小改动，直接用当前上下文执行 |
| 「继续上次没做完的登录」 | ✅ 加载上次契约 | 增量更新，只确认变化部分 |
| 「帮我看看这个报错是什么意思」 | ❌ 不需要 | 提问/咨询，不涉及执行 |
| 「帮我重构 auth 模块」 | ✅ 完整契约 | 即使有上下文，重构影响面大 |
| 「在这个文件里加个注释」 | ❌ 不需要 | 单文件微改动 |

### 判断规则

```
需要契约 = 以下任一条件满足:
  - 任务涉及 ≥ 3 个步骤
  - 任务涉及写文件 / 改代码 / 调外部 API
  - 任务涉及安全 / 数据 / 基础设施
  - 用户明确要求「帮我做 X」（执行型任务）
  - 上一次同一任务的契约超过 7 天（可能已过期）

不需要契约:
  - 纯问答 / 咨询
  - 单步微操作（改文案/加注释）
  - 用户已确认同一契约且对话未中断
```

---

## 7. 契约作为后续节点的唯一真相源

### 7.1 Execute — 从契约生成执行计划

Executor 的 System Prompt 不再拼凑片段，而是直接注入契约：

```
## 当前任务契约

**目标**: {contract.goal}
**范围**: 做 {contract.scope.in}，不要做 {contract.scope.out}
**约束**: {contract.constraints}
**风险边界**: {contract.risks} — 触及任一风险点必须暂停并询问
**权限**: 你可以 {contract.permissions}
**完工标准**: {contract.acceptance}

在上面边界内工作。超出边界 → 暂停并说明原因。不确定是否在边界内 → 暂停。
```

### 7.2 Checkpoint — 对照契约检查语义对齐

```
原 Planner 的 checkpoint 是对照「用户原始消息」→ 容易丢失上下文。

新 Checkpoint 对照「契约 + 用户原始消息」:
  - 执行结果是否满足 acceptance 的每一条？
  - 是否触及了 risks 而未暂停？
  - 是否超出了 scope.out 的边界？
  - 是否违反了 constraints 中的硬限制？
```

### 7.3 Reflector — 对照契约做质量审核

```
Reflector 不需要猜测「用户想要什么」，直接逐条对照契约:

for each acceptance_criterion in contract.acceptance:
    执行结果满足这条吗？[✓/✗]
    ✗ → 回 Execute，带上具体偏离说明

for each constraint in contract.constraints:
    产物是否遵守了这条约束？[✓/✗]
    ✗ → 回 Execute
```

### 7.4 交接卡 — 基于契约生成

会话完成时生成交接卡，契约是全结构化输入：

```
交接卡 = TaskContract + 本次执行状态

{
  "contract": { ... },              // 全量契约
  "status": {
    "completed": ["Login.tsx", "auth.ts"],
    "pending": ["后端 API 对接"],
    "decisions_made": ["bcrypt rounds=12", "JWT 7天"],
    "issues_open": ["CSRF 防护待确认"],
    "next_steps": ["写后端 API", "联调测试"]
  }
}
```

---

## 8. 数据结构设计

### 8.1 Python Pydantic 模型

```python
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class Scope(BaseModel):
    in_: list[str] = Field(default_factory=list, alias="in")
    out: list[str] = Field(default_factory=list)


class Permissions(BaseModel):
    read: str | list[str] = "project"      # "project" | "all" | ["src/**", ...]
    write: str | list[str] = "ask"         # "ask" | "none" | ["src/components/*", ...]
    execute: str | list[str] = "ask"       # "ask" | "none" | ["npm test", ...]
    api: list[str] = Field(default_factory=list)
    shell: list[str] = Field(default_factory=list)


class TaskContract(BaseModel):
    # ── 标识 ──
    contract_id: str              # UUID
    session_id: str               # 关联会话
    version: int = 1              # 增量更新时递增

    # ── 7 个核心字段 ──
    goal: str = ""                # 一句话最终目标
    scope: Scope = Field(default_factory=Scope)
    constraints: list[str] = Field(default_factory=list)
    acceptance: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    permissions: Permissions = Field(default_factory=Permissions)
    deliverables: dict = Field(default_factory=lambda: {
        "format": "代码改动",
        "artifacts": []
    })

    # ── 元信息 ──
    confidence: float = 0.0       # Planner 对完整度的评分
    status: str = "draft"         # draft | confirmed | executing | completed | archived
    missing_fields: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    confirmed_by_user: bool = False

    class Config:
        populate_by_name = True
```

### 8.2 PostgreSQL 存储

契约存为 JSONB 列，加在 `sessions` 表里（或单独一张表）：

```sql
-- 方案 A: 加在 sessions 表（简单，一个会话一个活跃契约）
ALTER TABLE sessions
ADD COLUMN task_contract JSONB,
ADD COLUMN contract_version INTEGER DEFAULT 0;

-- 方案 B: 独立表（支持契约历史）
CREATE TABLE task_contracts (
    id              TEXT PRIMARY KEY,      -- contract_id
    session_id      TEXT NOT NULL REFERENCES sessions(id),
    version         INTEGER NOT NULL DEFAULT 1,
    contract        JSONB NOT NULL,        -- 完整 TaskContract
    status          TEXT DEFAULT 'draft',
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    confirmed_at    TIMESTAMPTZ
);

CREATE INDEX idx_contracts_session ON task_contracts(session_id, version DESC);
```

推荐**方案 B**——契约要记录历史版本，方便回溯「用户上次确认了什么」。

---

## 9. 技术实现路线

### Phase 1: 核心模型 + Planner 升级（3-5 天）

```
1. 创建 models/task_contract.py (Pydantic 模型)
2. 升级 prompts/templates.py:
   - 新增 build_contract_system_prompt()
   - 新增 format_contract_for_executor()
3. 升级 core/graph.py planner_node:
   - 输出从 dimensions dict → TaskContract
   - 增加 confidence 计算逻辑
   - 增加 missing_fields 判断
4. 升级 core/graph.py clarify_node:
   - 追问对齐 contract 字段（缺什么问什么）
5. 数据库: 创建 task_contracts 表
6. 服务层: services/contract_store.py (CRUD)
```

### Phase 2: 前端契约卡片（2-3 天）

```
1. 契约卡片 UI 组件 (Vanilla JS):
   - 展示 7 个字段（可折叠）
   - scope.in / scope.out 左右对比布局
   - risks 红色高亮
   - 「确认」/「修改」按钮
2. SSE 事件: contract_update 事件类型
3. 用户交互: 点击字段 → 编辑 → 确认重新生效
```

### Phase 3: 下游节点接入（2-3 天）

```
1. Execute: System Prompt 模板注入契约
2. Checkpoint: 对照契约做语义对齐检查
3. Reflector: 逐条对照约束和验收标准
4. 交接卡: 基于契约状态生成
```

### Phase 4: 增量更新 + 版本管理（1-2 天）

```
1. 契约增量更新逻辑（用户说"改"时不重建）
2. contract_history 版本链
3. 跨会话加载上次契约
```

---

## 10. 常见反模式

### ❌ 反模式 1：契约写得太细

```
❌ 约束: "LoginButton 组件的颜色是 #D4AF37，hover 时变 #F0E68C，圆角 8px"
✅ 约束: "UI 风格与现有黑金主题一致"
```

契约是边界声明，不是详细设计文档。太细的契约：
- 用户不敢点确认（读不完）
- Agent 束手束脚（每个像素都要对照）
- 更新频繁（改个颜色就得改契约）

**粒度原则：契约约束 What / Why，不约束 How。**

### ❌ 反模式 2：偷懒不写 scope.out

```
❌ scope: {in: ["登录功能"]}
✅ scope: {in: ["用户名+密码登录"], out: ["OAuth", "邮箱验证", "权限管理"]}
```

没有 out，Agent 会往你认为理所当然不该做的方向跑。out 就是防偷懒。

### ❌ 反模式 3：每次都满血契约

```
用户: "把登录按钮的颜色改成 #D4AF37"
Alfred: （生成完整 7 字段契约……追问 3 个问题……）
用户: "我就改个颜色你在干嘛？？"
```

小任务不需要契约。参考第 6 节的判断规则。

### ❌ 反模式 4：用户说不清就放弃追问

```
用户: "帮我做那个功能，你知道的"
Alfred: "好的。"（然后就猜着做了 —— 必炸）
```

这种情况下 `goal.confidence` 必然 < 0.3，必须追问。追问方式从「开放式」变成「选择题」：

> "你说的应该是这两件事之一：A) 上次没做完的登录，B) 之前提过的评论功能。是哪件？"

### ❌ 反模式 5：契约确认后就当圣旨，拒绝变化

```
用户: "等一下，范围再加一个密码找回功能"
Alfred: "你的契约 scope.out 里写了不包含密码找回，不能加。" ← 不行
```

契约是**活的文档**，用户说改就得改。正确的做法：增量更新 → 检查改动是否影响其他字段 → 仅重算受影响的 `confidence` 和 `risks` → 快速确认 → 继续。

---

## 附录 A：与现有系统的对照

| 现有概念 | 在契约体系中的位置 |
|---------|------------------|
| `expressed_dimensions` dict | 被 TaskContract 完全替代，不再使用散装 dict |
| `completeness` 评分 | 升级为 `confidence`（0-1），对应 7 个字段的完整度加权 |
| `dimensions` 维度定义 | 不再是独立维度，而是映射到契约字段的缺失检测依据 |
| `clarify_questions` | 从「追问模板」改为「按契约缺失字段 + 风险优先级生成」 |
| Checkpoint `aligned` | 从「对照用户消息」改为「对照 contract.acceptance」 |
| Reflector `criteria` | 从「准确性/完整性/实用性」改为「约束遵守/标准满足/边界合规」 |

## 附录 B：与产品文档的对应

任务契约直接实现 [阿福产品规划](../docs/阿福) 中「1. 想清楚：任务澄清 → 任务契约」：

- 7 个字段直接对规划中的 7 个定义
- 追问策略对规划中的「缺什么问什么」
- 契约确认 UI 对规划中的「前端渲染任务契约为卡片」

同时也对应 [product-vision.md](./product-vision.md) Phase 1 的**长链自主执行**和 **HITL**（Human-in-the-Loop）——契约是人工审批和自动执行之间的边界协议。

---

*初稿: 2026-07-23 | 作者: Alfred + yoiwerr*
