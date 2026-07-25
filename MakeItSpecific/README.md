# 阿福 Alfred — AI 协作管家

> **守在用户与智能体之间的 AI 协作管家。**
> 帮助你想清楚目标、适配合适能力、规范工作过程、记住项目结果。

从 [Portal/MakeItSpecific](https://github.com/yoiwerr/portal) 独立出来的完整项目。

---

## 产品定位

阿福不是替用户做所有事情的自动执行 Agent，而是**人与智能体之间的协作管家**。其他 Agent 负责行动，阿福负责确保行动是对的。

### 四项核心能力

| 能力 | 一句话 |
|------|--------|
| 💡 **想清楚** | 目标不清晰时追问关键信息，形成任务契约 |
| 🤝 **选对人** | 根据任务特点推荐合适的模型、工具或 Agent |
| 🛡️ **看住过程** | 控制范围、规范节奏，高风险操作先确认 |
| 🧠 **记住结果** | 每次收尾生成项目交接卡，下次直接恢复上下文 |

---

## 运行流程

### 1. 环境准备

```bash
# 克隆项目
git clone https://github.com/yoiwerr/Alfred.git
cd Alfred
```

**前置依赖：**

- Python 3.12+
- PostgreSQL 16（需 pgvector 扩展）
- LLM API Key（至少一个）

### 2. 安装依赖

```bash
# pip 安装
pip install -r requirements.txt

# 或使用 uv（推荐，更快）
uv sync
```

### 3. 配置环境变量

```bash
cp .env.example .env
vim .env   # 填入 LLM API Key + PostgreSQL 密码
```

**必填项（至少配置一个 LLM Provider）：**

```bash
# LLM Provider — 至少填一个 API Key
LLM_PROVIDER=auto              # dashscope | deepseek | openai | local | auto
DASHSCOPE_API_KEY=sk-xxx       # 百炼 API Key（Embedding + Rerank 必须）
DEEPSEEK_API_KEY=sk-xxx        # DeepSeek API Key

# PostgreSQL（存储向量 + 会话 + 反馈）
PGSQLPASSWORD=your-pg-password
```

> 详细的全部环境变量说明见 [.env.example](./.env.example)。

### 4. 启动 PostgreSQL

**方式一：Docker（推荐，一键启动）**

```bash
docker run -d --name alfred-pg \
  -e POSTGRES_PASSWORD=yourpassword \
  -e POSTGRES_DB=alfred \
  -p 5432:5432 \
  pgvector/pgvector:pg16
```

**方式二：使用已有的 PostgreSQL 实例**

确保已安装 `pgvector` 扩展：
```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

### 5. 启动阿福

```bash
python app.py
```

启动成功后会看到：

```
============================================================
  Alfred — Provider: deepseek | Model: deepseek-chat
============================================================
  KB: 8 files, 156 chunks
  [OK] ready
```

访问：
- **前端界面**: http://localhost:8001
- **Swagger API 文档**: http://localhost:8001/docs
- **健康检查**: http://localhost:8001/api/health

### 6. 开始对话

在浏览器打开 http://localhost:8001，输入你的需求。阿福会：

1. **Router 理解意图** → 自动识别你在问什么场景
2. **RAG 检索知识库** → 从 `knowledge_base/` 中找到相关领域知识
3. **Planner 分析维度** → 提取关键需求，判断信息完整度
4. **信息不够就追问** → 用任务契约明确：目标、范围、约束、验收标准
5. **信息够了就执行** → ReAct Agent 调用工具完成任务
6. **Checkpoint 语义校准** → 检查输出是否与原始意图对齐
7. **Reflector 质检** → 评分并决定是否自动重试（最多 2 次）
8. **生成交接卡** → 任务完成时自动生成 Markdown 交接卡

---

## 架构

### 整体架构

```
Browser (SSE Token Streaming)
    │  POST /api/chat/stream?v=2
    ▼
FastAPI → LangGraph ReAct Agentic Loop
    │
    ├── Router:    意图识别 + 模块自动路由
    ├── Enrich:    Query 增强（上下文驱动，提升 RAG 命中率）
    ├── RAG:       混合检索（Dense + BM25 Sparse → RRF → Rerank）
    ├── Planner:   提取维度 + 判断完整度 → 追问 or 执行
    ├── Clarify:   动态追问补全信息（任务契约引导）
    ├── Engineering Check:  工程规范场景检测（建议/确认/阻断三级）
    ├── Execute:   ReAct Agent tool calling loop（支持并行 tool call）
    ├── Checkpoint: Planner 语义中枢介入，检查对齐
    └── Reflect:   质量检查 + 自动重试（最多 2 次）

存储层: PostgreSQL + PGVector（向量检索 + 会话 + 记忆 + 反馈 + 契约）
```

### LangGraph 执行流程

```
START
  │
  ▼
router (意图识别)
  │
  ▼
enrich (Query 增强)
  │
  ▼
rag (知识库检索)
  │
  ▼
planner (LLM 提取维度 + 完整度判断)
  ├─ 信息不足 → clarify (追问 → END)
  └─ 信息足够 → engineering_check
                    ├─ 阻断 → END
                    ├─ 多Agent → multi_agent_execute → reflect → END
                    └─ 正常 → execute
                                │
                                ▼
                            checkpoint (语义对齐检查)
                                ├─ 对齐 → reflect
                                └─ 偏离 → execute (重试)
                                            │
                                            ▼
                                        reflect (质量检查)
                                            ├─ 通过 → END
                                            └─ 不通过 → execute (重试，最多2次)
```

### 三层上下文架构

| 层 | 名称 | 内容 | 生命周期 |
|----|------|------|----------|
| L1 | 滑动窗口 | 最近 3 轮完整对话原文 | 当前会话 |
| L2 | 滚动摘要 | 全部历史的压缩总结 | 当前会话 |
| L3 | 语义事实 | LLM 提取的结构化事实，PGVector 持久化 | 跨会话 |

### 任务契约系统

在 Planner 阶段自动生成结构化任务契约：

```
任务契约
├── goal          → 一句话目标
├── scope         → 范围（in / out）
├── constraints   → 硬性约束
├── acceptance    → 验收标准
├── risks         → 风险登记
├── deliverables  → 交付物定义
└── permissions   → 权限声明（读/写/执行）
```

契约在前后端之间以 SSE 事件实时推送，持久化到 PostgreSQL，支持跨会话恢复。

### 多 Agent Panel（三立场并行）

当需求不明确但用户拒绝追问时，自动触发三立场并行分析：

| 立场 | 角色 | 关注点 |
|------|------|--------|
| 💼 实用派 | Focus on results | 最快能用的方案 |
| 🛡️ 稳健派 | Focus on safety | 最稳妥可维护的方案 |
| 💡 创新派 | Focus on possibilities | 最优雅前瞻的方案 |

三并行输出后，阿福整合为结构化对比并给出推荐。

---

## 项目目录

```
Alfred/
├── app.py                ← FastAPI 入口
├── config.py             ← 全局配置（多 Provider）
├── pyproject.toml        ← 项目元数据 + 依赖
├── requirements.txt      ← pip 依赖
├── .env.example          ← 环境变量模板
│
├── core/                 ← Agent 引擎
│   ├── agent.py          ← Agent 编排器（astream_events 流式）
│   ├── graph.py          ← LangGraph V4 ReAct Agentic Loop
│   ├── llm_client.py     ← 多 Provider LLM 工厂
│   ├── context_engine.py ← 三层上下文架构（L1/L2/L3）
│   └── router.py         ← 意图路由（规则 + LLM）
│
├── routers/              ← FastAPI 路由
│   ├── chat.py           ← 核心对话（SSE 流式，V2 token 级）
│   ├── sessions.py       ← 会话管理 + Markdown 导出
│   ├── knowledge.py      ← 知识库管理
│   ├── feedback.py       ← 用户反馈（👍👎）
│   ├── files.py          ← 文件上传
│   └── handover.py       ← 交接卡生成
│
├── services/             ← 数据服务
│   ├── rag_service.py       ← RAG V5（来源感知 + 混合检索 + 知识图谱）
│   ├── vector_store.py      ← PGVector 向量存储
│   ├── session_store.py     ← PostgreSQL 会话持久化
│   ├── contract_store.py    ← 任务契约持久化
│   ├── document_processor.py ← 文档解析 + 语义分块
│   ├── engineering_advisor.py ← 工程规范顾问
│   ├── multi_agent.py       ← 三立场 Agent Panel
│   ├── handover_service.py  ← 交接卡服务
│   └── md_export.py         ← Markdown 导入导出
│
├── tools/                ← Agent 工具集（@tool）
│   └── search.py         ← search_kb / search_web / search_history
│
├── skills/               ← 技能（提示词工程 / 工作安排 / 信息留存 / 代码审查）
├── prompts/              ← System Prompts（Planner / Executor / Reflector）
├── models/               ← Pydantic 数据模型（含 task_contract）
├── memory/               ← L2/L3 记忆系统（SessionMemory + UserProfile）
│
├── static/               ← 前端（Vanilla JS + CSS，零框架依赖）
│   ├── index.html        ← 三栏工作台布局
│   ├── css/style.css
│   ├── js/chat.js        ← SSE token 流式渲染 + 反馈 + 交接卡
│   └── source/           ← 静态资源
│
├── knowledge_base/       ← RAG 知识源（.md 文件，含 frontmatter 元数据）
│   ├── prompt_engineering.md
│   ├── workflow_best_practices.md
│   ├── tool_recommendations.md
│   ├── tech_news.md
│   ├── engineering/      ← 工程规范知识卡片
│   └── coding_skills/
│
├── tests/                ← 测试
└── data/                 ← 运行时数据（日志 + 导出，自动创建）
```

---

## 技术栈

| 层 | 技术 |
|----|------|
| 框架 | FastAPI + LangGraph + LangChain |
| LLM | 多 Provider — DashScope (Qwen) / DeepSeek / OpenAI / Local |
| 嵌入 | DashScope text-embedding-v4（1024 维） |
| 向量存储 | PostgreSQL + PGVector |
| Rerank | 百炼 qwen3-rerank（120K token / 500 docs） |
| 检索管道 | Dense + BM25 Sparse → RRF 融合 → Rerank → 关键词加权 → 邻接 Chunk 召回 |
| 分块 | SemanticChunker（相邻句子 embedding 相似度断崖切分） |
| 流式 | SSE（sse-starlette），astream 节点级进度 + token 级渲染 |
| 会话 | PostgreSQL（与向量存储共用实例） |
| 记忆 | L2 滚动摘要 + L3 语义事实（LLM 提取 + PGVector 持久化） |
| 前端 | Vanilla JS + CSS（零框架依赖，三栏工作台布局） |

---

## API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/` | 首页（三栏工作台） |
| `GET` | `/api/health` | 健康检查（含 PG + Agent 状态） |
| `POST` | `/api/chat/stream?v=2` | SSE 流式对话（V2 token 级渲染） |
| `GET` | `/api/sessions` | 会话列表 |
| `GET` | `/api/sessions/{id}` | 会话详情（含消息历史） |
| `GET` | `/api/sessions/{id}/export` | 导出 Markdown 交接卡 |
| `DELETE` | `/api/sessions/{id}` | 删除会话 |
| `POST` | `/api/sessions/{id}/handover` | 生成交接卡 |
| `POST` | `/api/feedback` | 提交反馈（👍👎 + 评论文本） |
| `GET` | `/api/feedback/stats` | 反馈统计 |
| `POST` | `/api/knowledge/upload` | 上传知识文件 |
| `POST` | `/api/files/upload` | 上传附件 |
| `GET` | `/docs` | Swagger API 文档 |

---

## 开发

### 运行测试

```bash
python -m pytest tests/ -v
```

### 添加知识库文件

在 `knowledge_base/` 下放置 `.md` 文件，支持 YAML frontmatter 元数据：

```markdown
---
source_title: 我的参考文档
source_url: https://example.com/doc
source_type: documentation
repository: https://github.com/user/repo
author: 作者名
---
正文内容...
```

重启后阿福会自动索引新文件。

### 添加新 Skill

1. 在 `skills/` 下创建新的 Skill 类（继承 `BaseSkill`）
2. 在 `core/agent.py` 的 `__init__` 中注册
3. 在 `prompts/system_prompts.py` 中添加对应的 System Prompt

---

## Docker 部署

```bash
# 1. 配置环境变量
cp .env.example .env && vim .env

# 2. 启动 PostgreSQL
docker run -d --name alfred-pg \
  -e POSTGRES_PASSWORD=yourpassword \
  -e POSTGRES_DB=alfred \
  -p 5432:5432 \
  pgvector/pgvector:pg16

# 3. 启动 Alfred
python app.py
# → http://localhost:8001
```

---

## License

MIT
