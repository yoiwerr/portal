# MakeItSmooth 企业级 Agent 能力清单

> 注：✅ 已实现  🔧 部分实现  ❌ 待开发

---

## 一、Tools（原子能力 — Agent 直接调用的 @tool 函数）

### 1.1 信息检索 (Retrieval)

| Tool | 状态 | 说明 |
|------|------|------|
| `search_knowledge_base` | ✅ | ChromaDB 向量检索本地知识库，DashScope text-embedding-v3 |
| `search_web` | 🔧 | **占位符**。需接入 Tavily Search API 或 Brave Search API |
| `search_chat_history` | 🔧 | SQLite 关键词匹配，需升级为向量检索（用 ChromaDB 存对话 embedding） |
| `search_codebase` | ❌ | **新增**：对当前工作目录做代码搜索（grep/ast-grep），找函数定义、引用关系 |
| `fetch_url` | ❌ | **新增**：抓取指定 URL 内容并转为 Markdown，用于阅读在线文档 |

### 1.2 文件系统 (File System)

| Tool | 状态 | 说明 |
|------|------|------|
| `read_file` | ❌ | 读取文件内容（限制在项目目录内），支持 .md/.py/.json/.csv/.log 等 |
| `write_file` | ❌ | 写入文件，需用户确认（安全），写入后返回路径 |
| `list_directory` | ❌ | 列出目录结构，支持递归和深度控制 |
| `search_files` | ❌ | 按文件名 glob 搜索，按内容 grep 搜索 |
| `delete_file` | ❌ | 删除文件，需用户确认 |
| `watch_file` | ❌ | 监控文件变化（长时间任务用），用于实时日志分析等场景 |

### 1.3 代码执行 (Code Execution)

| Tool | 状态 | 说明 |
|------|------|------|
| `python_exec` | ❌ | 沙箱执行 Python 代码片段，返回 stdout/stderr + 返回值。超时 30s，内存限制。需要 `SANDBOX_ENABLED=true` |
| `run_shell` | ❌ | **高风险**：执行 Shell 命令（`ls`, `git log`, `cat`, `pip list` 等只读命令）。可写命令需用户确认 |
| `run_test` | ❌ | 运行 pytest 并返回结果，用于「写完代码→验证」的闭环 |

### 1.4 知识管理 (Knowledge Management)

| Tool | 状态 | 说明 |
|------|------|------|
| `add_to_knowledge_base` | ❌ | 将一段文本（通常是对话中提炼的知识点）写入 ChromaDB，下次可检索到 |
| `summarize_text` | ❌ | 对长文本（文章、日志、代码库）做摘要，用 LLM 分段总结 |
| `extract_entities` | ❌ | 从文本中提取关键实体：人名、项目名、技术栈、日期、决策点 |

### 1.5 数据处理 (Data Processing)

| Tool | 状态 | 说明 |
|------|------|------|
| `parse_file` | ❌ | 自动检测文件类型并解析：CSV→DataFrame, JSON→dict, PDF→text, Excel→DataFrame |
| `generate_chart` | ❌ | 用 matplotlib/plotly 生成图表，返回 base64 PNG 或 HTML |
| `compare_texts` | ❌ | Diff 对比两个文本/文件，输出差异报告 |

### 1.6 项目管理 (Project Management)

| Tool | 状态 | 说明 |
|------|------|------|
| `create_todo_list` | ❌ | 创建结构化待办清单，持久化到 SQLite，支持状态流转 |
| `get_todo_status` | ❌ | 查询待办清单的完成情况 |
| `create_timeline` | ❌ | 生成甘特图式的时间线（Mermaid/HTML），可视化项目进度 |

### 1.7 外部集成 (External Integration)

| Tool | 状态 | 说明 |
|------|------|------|
| `github_search` | ❌ | 搜索 GitHub 仓库/Issues/PRs，需要 `GITHUB_TOKEN` |
| `github_create_issue` | ❌ | 在指定仓库创建 Issue |
| `github_read_code` | ❌ | 读取 GitHub 上指定文件（不 clone 整个仓库） |

---

## 二、Skills（复合能力 — 组合多个 Tool 的高层技能）

### 2.1 已有 Skill（升级版）

| Skill | 状态 | 升级方向 |
|-------|------|----------|
| **Prompt Studio** (原 prompt_refiner) | ✅ | 加入联网搜索最新提示词技巧，可选不同模型策略对比 |
| **Project Planner** (原 work_arranger) | ✅ | 输出存入文件 + 自动生成 TODO + 可追踪进度 |
| **Knowledge Curator** (原 info_retention) | ✅ | 自动提炼对话关键信息 → 写入 KB → 下次检索到 |

### 2.2 新增 Skill

| Skill | 工具组合 | 场景 |
|-------|----------|------|
| **Code Reviewer** | read_file + search_codebase + search_web + search_kb | 审查代码质量/安全/性能，输出分级的 Review 报告 |
| **Data Analyst** | read_file + parse_file + python_exec + generate_chart + write_file | 拖入 CSV/JSON → 分析 → 图表 → Markdown 报告 |
| **Research Assistant** | search_web + fetch_url + summarize_text + compare_texts + write_file | 多源调研 → 交叉验证 → 对比分析 → 输出调研报告 |
| **Bug Investigator** | read_file + search_codebase + run_shell + python_exec + search_web | 读日志/读代码 → 假设 → 验证 → 定位根因 + 修复建议 |
| **Technical Writer** | read_file + search_codebase + search_kb + write_file | 读代码库 → 生成 API 文档 / README / CHANGELOG |
| **Deployment Advisor** | search_kb + search_web + read_file + write_file | 分析项目结构 → 推荐部署方案 → 生成 docker-compose / k8s yaml |
| **Daily Standup** | search_chat_history + search_kb + summarize_text + create_timeline | 回顾昨日对话 → 整理今日计划 → 生成站会报告 |

---

## 三、RAG 知识库数据方向

### 3.1 现有

```
knowledge_base/
├── prompt_engineering.md         ✅ 提示词工程最佳实践
├── tech_news.md                  ✅ 技术趋势（2026 模型、框架、工具）
└── workflow_best_practices.md    ✅ 工作流与项目管理方法论
```

### 3.2 计划新增（按优先级排列）

```
knowledge_base/
│
├── 01-programming/               ← 编程语言
│   ├── python_best_practices.md  Python 编码规范、类型系统、异步、性能
│   ├── typescript_guide.md       TS 类型体操、工程化配置
│   └── rust_for_pythonistas.md   Rust 入门（面向 Python 开发者）
│
├── 02-architecture/              ← 架构设计
│   ├── microservices_patterns.md 微服务设计模式（CQRS、Event Sourcing、Saga）
│   ├── api_design_guide.md       REST/GraphQL/gRPC 选型 + 最佳实践
│   └── database_selection.md     SQL vs NoSQL vs NewSQL 决策树
│
├── 03-devops/                    ← DevOps
│   ├── docker_best_practices.md  Dockerfile 优化、多阶段构建、安全
│   ├── k8s_deployment.md         K8s 部署模式（Deployment、StatefulSet、Job）
│   ├── ci_cd_pipeline.md         GitHub Actions / GitLab CI 模板库
│   └── observability_stack.md    Prometheus + Grafana + Loki 搭建指南
│
├── 04-frontend/                  ← 前端
│   ├── react_patterns_2026.md    React 19+ 最佳实践（RSC、Server Actions）
│   ├── css_architecture.md       Tailwind/CSS Modules/CSS-in-JS 对比
│   └── frontend_performance.md   Core Web Vitals 优化清单
│
├── 05-ai-ml/                     ← AI/ML 工程
│   ├── llm_deployment.md         LLM 部署方案（vLLM/SGLang/Ollama）
│   ├── rag_optimization.md       RAG 优化技巧（分块策略、检索增强、重排序）
│   ├── agent_design_patterns.md  Agent 设计模式（ReAct/Plan-Execute/多Agent）
│   └── prompt_engineering_advanced.md  进阶提示词技巧（结构化输出、思维树、Self-Consistency）
│
├── 06-security/                  ← 安全
│   ├── owasp_top10_2026.md       OWASP Top 10 及修复方案
│   ├── api_security.md           JWT/OAuth2/CORS/CSRF 安全实践
│   └── supply_chain_security.md  依赖审计、SBOM、镜像签名
│
├── 07-project-management/        ← 项目管理
│   ├── agile_scrum_guide.md      Scrum 实战（Sprint 规划、Retro 模板）
│   ├── technical_writing.md      技术文档规范（API文档、README、RFC）
│   └── engineering_ladder.md     技术职级与成长路径参考
│
└── 08-performance/               ← 性能优化
    ├── web_performance.md        前端性能优化清单
    ├── database_optimization.md  索引优化、查询调优、连接池
    └── caching_strategies.md     Redis/CDN/浏览器缓存 策略对比
```

---

## 四、MCP 集成

| MCP Server | 用途 | 优先级 | 配置 |
|------------|------|--------|------|
| **GitHub MCP** | Issues/PRs/Repo/Code 操作 | 🔴 高 | `GITHUB_TOKEN` |
| **File System MCP** | 安全访问本地文件系统 | 🔴 高 | 无需额外配置（本地 MCP） |
| **Tavily MCP** | 联网搜索（替代自定义 API 调用） | 🔴 高 | `TAVILY_API_KEY` |
| **Postgres MCP** | 查询 PostgreSQL 数据库 | 🟡 中 | 数据库连接串 |
| **Notion MCP** | 读写 Notion 文档/数据库 | 🟡 中 | `NOTION_API_KEY` |
| **Slack MCP** | 发送消息/读取频道 | 🟢 低 | `SLACK_BOT_TOKEN` |
| **Brave Search MCP** | 隐私友好的联网搜索 | 🟢 低 | `BRAVE_SEARCH_API_KEY` |
| **Context7 MCP** | 获取最新库/框架文档 | 🟢 低 | 免费 |

---

## 五、API Key 矩阵

### 5.1 LLM（至少一个）

| Key | 用途 | 获取方式 |
|-----|------|----------|
| `DASHSCOPE_API_KEY` | 阿里通义千问 | https://dashscope.console.aliyun.com |
| `DEEPSEEK_API_KEY` | DeepSeek | https://platform.deepseek.com |
| `OPENAI_API_KEY` | OpenAI GPT-4o | https://platform.openai.com |
| `ANTHROPIC_API_KEY` | Claude（备选） | https://console.anthropic.com |

### 5.2 搜索

| Key | 用途 | 获取方式 |
|-----|------|----------|
| `TAVILY_API_KEY` | 联网搜索（最推荐） | https://tavily.com（免费额度 1000/月） |
| `BRAVE_SEARCH_API_KEY` | 备选搜索方案 | https://brave.com/search/api/ |

### 5.3 外部集成

| Key | 用途 | 获取方式 |
|-----|------|----------|
| `GITHUB_TOKEN` | GitHub MCP / API | https://github.com/settings/tokens |
| `NOTION_API_KEY` | Notion MCP | https://www.notion.so/my-integrations |

### 5.4 可观测性

| Key | 用途 | 获取方式 |
|-----|------|----------|
| `LANGFUSE_PUBLIC_KEY` | LLM 调用追踪 | https://cloud.langfuse.com（免费层） |
| `LANGFUSE_SECRET_KEY` | LLM 调用追踪 | 同上 |

### 5.5 .env 最终形态

```bash
# === LLM (至少填一个) ===
LLM_PROVIDER=auto
DASHSCOPE_API_KEY=sk-xxx
DEEPSEEK_API_KEY=sk-xxx
OPENAI_API_KEY=sk-xxx

# === 搜索 ===
TAVILY_API_KEY=tvly-xxx

# === 外部集成 (可选) ===
GITHUB_TOKEN=ghp_xxx
NOTION_API_KEY=secret_xxx

# === 可观测性 (可选) ===
LANGFUSE_PUBLIC_KEY=pk-xxx
LANGFUSE_SECRET_KEY=sk-xxx

# === 沙箱 ===
SANDBOX_ENABLED=false         # python_exec 安全开关
```

---

## 六、文件系统能力矩阵

| 能力 | Agent 可见 | 说明 |
|------|-----------|------|
| **工作目录** | 启动时指定 `WORK_DIR`，Agent 只能在这个目录内操作 | 安全隔离 |
| **读文件** | ✅ 支持 .md .py .js .ts .json .yaml .csv .log .txt .html .css | 二进制文件转 base64 |
| **写文件** | ✅ 需用户确认（每个文件弹窗或白名单目录） | 防恶意写入 |
| **目录遍历** | ✅ `list_directory` 支持 depth 参数 | 默认 depth=2 |
| **搜索文件** | ✅ glob + grep，返回匹配行 + 上下文 | 限制返回数量（50条） |
| **文件监控** | 🔮 `watch_file` 用于 tail -f 式日志分析 | 长任务 |
| **拖拽上传** | 🔮 前端支持拖拽文件到聊天框 → 自动读取内容 | UX |
| **批量导出** | ✅ 已有 `md_export.py`，对话导出为 .md | 扩展到 .pdf |

---

## 七、实施路线图

```
阶段 B (工具生态) ────────────────────────────────────────── Week 2-3
│
├── B1: 核心工具上线
│   ├── read_file / write_file / list_directory / search_files
│   ├── search_web 接入 Tavily
│   ├── python_exec 沙箱
│   └── 工具注册表重构 (tools/registry.py)
│
├── B2: 记忆系统
│   ├── L2 跨会话记忆 (session_memory.py)
│   ├── L3 用户画像 (user_profile.py)
│   └── summarize_text / add_to_knowledge_base tools
│
├── B3: Knowledge Base 扩展
│   ├── 按 3.2 清单编写 10-15 个 .md 知识文件
│   └── 知识库自动更新脚本
│
└── B4: 前端统一对话入口
    ├── 去掉三卡片 → 自由输入 + 快捷能力标签
    └── 拖拽上传文件

阶段 C (产品化 + 集成) ──────────────────────────────────── Week 4-5
│
├── C1: MCP 集成
│   ├── GitHub MCP
│   └── Tavily MCP
│
├── C2: 可观测性
│   ├── LangFuse 追踪
│   └── Token 用量 / 成本统计
│
├── C3: 产品化
│   ├── API Key 鉴权中间件
│   ├── 限流中间件
│   └── 审计日志
│
└── C4: 新 Skill 注册机制
    ├── YAML 声明式 Skill（skills/*.yaml）
    └── 前端自动发现新 Skill
```
