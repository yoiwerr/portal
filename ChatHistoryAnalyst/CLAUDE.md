# ChatLab (ChatHistoryAnalyst)

> Portal 子项目。外层运维见 [../CLAUDE.md](../CLAUDE.md)。

## 项目定位

AI 聊天记录深度分析引擎 — 上传聊天记录（纯文本格式），AI 自动输出量化心理指数、关系动力学诊断和行动建议。

三个核心 Skill Agent：
1. **人物画像 + 语气克隆** — 分析语气指纹（用词偏好、句式特征、口头禅），模仿对方回复
2. **情感心理指数** — 真诚指数 / 回避指数 / 冷暴力指数 / 情绪稳定性 + 主导情绪 + 情感趋势
3. **关系动力学** — 掌控力分配 / 关系进度条(4维) / 沟通姿态诊断 / 行动建议卡片

## 设计理念

### Context Engineering 架构

```
原始消息 ──→ context_engineer.py ──→ pgvector (3 个 collection)
                                           │
              ┌────────────────────────────┘
              ▼
    ┌─────────────────────┐
    │  psychology_knowledge │  ← 心理学参考资料 (data/*.txt)
    │  chat_history         │  ← 原始消息 + 上下文窗口
    │  context_analysis     │  ← 结构化统计数据 (自动生成)
    └─────────────────────┘
              │
              ▼
    ┌─────────────────────┐
    │  Tool Layer (4 tools) │
    │  · search_psychology_knowledge
    │  · search_chat_context      ← 搜结构化指标 (优先), fallback 原始消息
    │  · deep_read_message        ← 按需深读原文
    │  · web_search               ← Tavily 联网
    └─────────────────────┘
              │
              ▼
    ┌─────────────────────┐
    │  Skill Agents         │
    │  LLM 通过工具获取结构化指标 + 深读原文 + 心理学理论
    │  输出量化指数 JSON
    └─────────────────────┘
```

**核心思想**：代码只做数据计算，LLM 负责语义解读。
1. `context_engineer.py` 输出纯结构化指标（消息量、响应秒数、发起次数…），不做任何"这意味着什么"的判断
2. Agent 运行时通过 `search_chat_context` 检索原始统计数据
3. LLM 根据 System Prompt 中的「指标解读标准」自行判断（如：响应 > 6h → 回避信号）
4. 需要原文细节时调用 `deep_read_message` 精准检索

### 指数化 vs 定性描述

旧版输出（"气氛紧张"、"情感消极"）→ 新版输出量化指数（0-100）：

| Skill | 输出 |
|-------|------|
| 情感心理指数 | 真诚指数 + 回避指数 + 冷暴力指数 + 情绪稳定性 + 主导情绪 + 情感趋势 |
| 关系动力学 | 掌控力分配(%) + 关系进度条(确定性/暧昧度/亲近度/可能性) + 沟通姿态 + 行动建议(分类+优先级) |

每个指数有明确的分级区间定义（0-30/31-60/61-85/86-100），Agent System Prompt 中包含完整的分级解读和指标解读标准（阈值表格），确保输出一致性。

## 技术栈

| Layer | Tech | 备注 |
|-------|------|------|
| Language | Python 3.12, managed with `uv` | `pyproject.toml` + `uv.lock` |
| Backend | FastAPI + Uvicorn | 8 个 REST 端点 |
| Frontend | Streamlit | Neo-Minimal Dark 主题 |
| LLM | DeepSeek via OpenAI-compatible API | `deepseek-chat` |
| Agent FW | LangChain `create_agent` | 每个 Skill 独立 Agent 实例 |
| Vector DB ×3 | PostgreSQL + pgvector | 3 个 collection (psychology_knowledge / chat_history / context_analysis) |
| Embeddings | DashScope `text-embedding-v3` | 1024 维固定 |
| Web Search | Tavily Search API | `max_results=3` |
| Observability | LangSmith | 可选 |

### Python 依赖

```
dashscope, fastapi, langchain, langchain-community, langchain-openai,
langchain-postgres[async], langchain-tavily, langchain-text-splitters,
psycopg2-binary, pydantic, python-dotenv, streamlit, uvicorn
```

## 架构

```
Browser (Streamlit :8501)
        │
        ▼
FastAPI (:8000) ── src/main.py
        │
        ├── /          → portal/static/index.html  (首页)
        ├── /chatlab   → 302 → localhost:8501      (线上 nginx 拦截)
        ├── /css/*     → portal/static/css/
        └── /api/v1/*  → 8 个业务端点
        │
        ├── src/schemas.py             Pydantic models (含指数体系)
        ├── src/core_llm.py            LLM 实例 (DeepSeek via ChatOpenAI)
        ├── src/context_engineer.py    消息预处理 pipeline
        │
        ▼
    Skill Agents (src/skills/)
        ├── skill01_imitate.py     → {"reply": "...", "speech_fingerprint": "..."}
        ├── skill02_emotion.py     → EmotionIndices (6项指数 + 指标解读标准)
        └── skill03_atmosphere.py  → RelationDynamics (掌控力+进度条+建议 + 权力动态标准)
        │
        ▼
    Tools (src/tools.py) — 4 个 tool
        ├── search_psychology_knowledge()  → knowledge_store
        ├── search_chat_context()          → context_analysis_store (优先) + chat_history fallback
        ├── deep_read_message()            → chat_history_store (按需深读原文)
        └── web_search()                   → Tavily
        │
        ▼
    PGVector (src/rag_function.py) — 3 个 collection
        ├── knowledge_store        collection="psychology_knowledge"
        ├── chat_history_store     collection="chat_history"
        └── context_analysis_store collection="context_analysis"
```

## File Map

| File | Role | 修改频率 |
|------|------|----------|
| `src/main.py` | FastAPI app — 8 endpoints + 首页挂载 + /chatlab 重定向。仅支持 txt/json/md 纯文本上传 | 中 |
| `src/core_llm.py` | `base_llm` (deepseek-chat via ChatOpenAI)。同时加载 ChatLab/.env 和 portal/.env | 低 |
| `src/schemas.py` | Pydantic: ChatMessage, AnalysisRequest, EmotionIndices(6项指数), RelationProgress, RelationDynamics, ActionSuggestion, ImportRequest, FileUploadResponse | 中 |
| `src/context_engineer.py` | 消息预处理 pipeline: engineer_chat_context() 输出纯结构化指标（无语义解读）+ build_message_index_docs() | 高 |
| `src/tools.py` | 4 个 LangChain `@tool` + RELEVANCE_THRESHOLD=0.3。search_chat_context 返回原始数据 | 中 |
| `src/rag_function.py` | PGVector 三库管理 (knowledge / chat_history / context_analysis)、去重、分块、维度检查、context engineering 集成 | 高 |
| `src/skills/skill01_imitate.py` | 语气克隆 + 语气指纹 → `{"reply", "speech_fingerprint"}` | 中 |
| `src/skills/skill02_emotion.py` | 情感心理指数 → `EmotionIndices`。Prompt 含指标解读标准(响应时间/消息比例阈值表) | 中 |
| `src/skills/skill03_atmosphere.py` | 关系动力学 → `RelationDynamics`。Prompt 含权力动态解读标准(比例/响应/发起终结阈值表) | 中 |
| `front/frontend.py` | Streamlit UI: 文件上传(txt/json/md)、手动输入、指数仪表盘、进度条、建议卡片。全宽结果展示 | 高 |
| `docs/如何导入正确格式.md` | 导入格式说明 + 万能 AI 提示词（用户复制给任意大模型即可格式化原始聊天记录） | 低 |
| `import_knowledge.py` | 一次性脚本: data/*.txt → knowledge_store | 低 |
| `data/*.txt` | 心理学参考: 依恋(DBL)、沟通(communication)、深度关系(deeprelation)、模仿(imitate)、关系(relationship) | 低 |
| `pyproject.toml` | Python 依赖 | 低 |
| `docker-compose.yml` | postgres + api + streamlit | 低 |
| `Dockerfile` | Python 3.12 镜像 | 低 |
| `.env.example` | 密钥模板 (DEEPSEEK_API_KEY, DASHSCOPE_API_KEY, PGSQLPASSWORD, TAVILY_API_KEY, DB_HOST=localhost) | 低 |

## API 端点

| Method | Path | Request/Response | 说明 |
|--------|------|-----------------|------|
| POST | `/api/v1/import_chat` | `ImportRequest` → `{status, message, data}` | JSON/Text 聊天记录导入 |
| POST | `/api/v1/upload_chat_file` | `multipart/form-data` → `FileUploadResponse` | 文件上传 (仅 txt/json/md 纯文本) |
| POST | `/api/v1/imitate` | `AnalysisRequest` → `{reply, speech_fingerprint}` | Skill 1: 语气模仿+指纹 |
| POST | `/api/v1/emotion_analyze` | `AnalysisRequest` → `EmotionIndices` | Skill 2: 6项心理指数 |
| POST | `/api/v1/analyze_atmosphere` | `AnalysisRequest` → `RelationDynamics` | Skill 3: 关系动力学 |
| POST | `/api/v1/add_memory` | `AnalysisRequest` → `{status, message}` | 聊天记录写入向量库 (含 context engineering) |
| POST | `/api/v1/import_knowledge` | `?file_name=xxx.txt` → `{status, message}` | 知识文件导入 |
| GET | `/api/v1/imported_files` | → `{status, imported_files}` | 已导入知识文件列表 |
| DELETE | `/api/v1/clear_vector_store` | → `{status, message}` | 清空所有向量表 |

## 关键约定

### Agent 模式
```python
agent_executor = create_agent(model=base_llm, tools=ALL_TOOLS)
result = await agent_executor.ainvoke({"messages": [sys_msg, user_msg]})
raw_output = result["messages"][-1].content
```

### JSON 安全提取
```python
json_match = re.search(r'\{.*\}', raw_output, re.DOTALL)
clean = json_match.group(0)
return Model.model_validate_json(clean)
```

### PGVector 三库管理
- `psychology_knowledge` — 心理学参考书 (type="reference_book", source=文件名)
- `chat_history` — 原始消息 (type="chat_history", target_person, sender, timestamp)
- `context_analysis` — 结构化指标 (type="context_analysis", subtype="conversation_metrics")
- 全部惰性初始化 (`get_*_store()`)，避免模块导入时 DB 不可达导致 API 无法启动
- Embedding 维度固定 1024 (text-embedding-v3)

### Context Engineering 原则
- `context_engineer.py` 只输出纯数据（消息量、响应秒数、发起次数…），不做语义判断
- 指标解读标准（阈值、含义）全部写在 Skill 的 System Prompt 中，LLM 自行判断
- 调参只需改 Prompt 文本，不需要改 Python 代码

### Context Engineering 触发
- `save_chats_to_long_term_memory()` 写入原始消息后自动调用 `engineer_chat_context()` + `build_message_index_docs()`
- 即使 context engineering 失败也不会阻塞原始消息写入

### 去重策略
- 原始消息: 按 `sender|timestamp|content[:50]` 去重
- 知识文件: 按 `metadata.source` 检测是否已导入

### Chunking
- 知识文件: 500 字符 + 50 重叠 (RecursiveCharacterTextSplitter)
- 原始消息: 每条消息附带前后各 3 条作为上下文 (`CONTEXT_WINDOW=3`)

### Relevance Threshold
- 0.3 (所有工具共用)

### 前端约定
- Streamlit Neo-Minimal Dark 主题 (CSS 变量驱动)
- 结果展示全宽（双栏布局外独立区域），max-width 1400px
- 手动输入框 250px 高，消息预览容器 350px 高，格式说明 expander min-height 400px
- 指数可视化: 彩色进度条 (绿/黄/红梯度)
- 关系进度条: 4 列并排数值 + 进度条
- 行动建议: emoji 分类卡片 (⚡立即行动 / 🌱长期策略 / ⚠️风险预警) + ●○ 优先级

### 文件上传
- 仅接受纯文本格式: `.txt` / `.json` / `.md`
- 不支持图片、截图等二进制格式 — 用户需通过 `docs/如何导入正确格式.md` 中的万能提示词让 AI 转换

## 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `DEEPSEEK_API_KEY` | DeepSeek API 密钥 **(必填)** | — |
| `DEEPSEEK_MODEL` | DeepSeek 模型名 | `deepseek-chat` |
| `DEEPSEEK_BASE_URL` | DeepSeek API 地址 | `https://api.deepseek.com` |
| `DASHSCOPE_API_KEY` | DashScope API 密钥（Embedding 用） | — |
| `TAVILY_API_KEY` | Tavily 联网搜索密钥 | — |
| `PGSQLPASSWORD` | PostgreSQL 密码 | — |
| `DB_HOST` | PostgreSQL 地址 | `localhost` |
| `DB_PORT` | PostgreSQL 端口 | `5432` |

> `.env` 加载顺序: ChatLab/`.env` → portal/`.env`（后者 override）

## 本地开发

```bash
cd ~/portal
make dev                           # 一键: FastAPI (:8000) + MakeItSpecific (:8001)
# ChatLab FastAPI 会自动启动。
# 或手动:
cd ~/portal/ChatHistoryAnalyst
uv run uvicorn src.main:app --reload        # 终端 1
uv run streamlit run front/frontend.py       # 终端 2
```

打开 `http://localhost:8000`。

## 首次准备

```bash
uv sync                              # 装依赖
cp .env.example .env && vim .env     # 填 API 密钥 (DEEPSEEK_API_KEY, PGSQLPASSWORD, TAVILY_API_KEY)
uv run python import_knowledge.py    # 导入知识库（需 PostgreSQL + pgvector）
```

## Claude 使用指南

### 修改 Skill 时的要点
1. **System Prompt 是核心** — 指数定义的分级区间(0-30/31-60/...) + 指标解读标准（阈值表格）必须写在 prompt 里，不能只靠 JSON Schema
2. **Schema 用 `model_json_schema()` 动态生成** — 不要手写 JSON Schema 字符串
3. **每个 Skill 独立 Agent 实例** — 不要共享
4. **输出解析用 `re.search(r'\{.*\}', raw, re.DOTALL)`** — 不要用 split
5. **指标解读标准原则** — 调参数改 System Prompt 文本，不要改 context_engineer.py 里写死的 if/else

### 修改 tools 时的要点
1. **Tool description 要告诉 LLM 什么时候该调用** — 写清楚输入参数含义和适用场景
2. **`search_chat_context` 返回原始统计数据** — 不含预判解读，LLM 根据 Prompt 中的标准自行判断
3. **`search_chat_context` 优先搜 context_analysis** — 无结果自动 fallback 到 chat_history
4. **`deep_read_message` 是补充工具** — 不要让它替代 search_chat_context
5. **所有 tool 返回纯文本字符串** — 避免 LLM 400 错误

### 新增 collection 的步骤
1. `src/rag_function.py` — 添加 `_xxx_store` 懒加载变量 + `get_xxx_store()` + `__getattr__` 支持
2. `clear_vector_stores()` — 重置对应全局变量
3. 如需在 context engineering 中写入 → 修改 `save_chats_to_long_term_memory()`

### 调试技巧
- 查看 tool 调用日志: 终端搜索 `🛠️ [Tool]`
- 查看 context engineering 日志: 搜索 `Context Engineering`
- FastAPI 错误日志: 搜索 `Error in xxx skill`
- 维度不匹配: 调 `DELETE /api/v1/clear_vector_store` 后重新导入
- LLM 调用失败: 检查 `.env` 中 `DEEPSEEK_API_KEY` 是否正确；确认加载了 portal/.env（`run_dev.py` 会 cd 到 ChatLab/）

## Session 记录

### 2026-07-09 (afternoon) — LLM 切换 + 架构解耦 + 前端重构

1. **LLM 切换: Qwen → DeepSeek** — `core_llm.py` 从 ChatTongyi 改为 ChatOpenAI 指向 DeepSeek API；`DEEPSEEK_API_KEY` / `DEEPSEEK_MODEL` / `DEEPSEEK_BASE_URL` 环境变量
2. **context_engineer 纯数据化** — 删除所有硬编码 if/else 语义判断（"⚠️消息量严重不对等"等），只输出原始统计数据（消息量、比例、响应秒数、发起/终结次数、逐轮时序）。代码量从 ~260 行减到 ~210 行
3. **指标解读移入 Prompt** — skill02/03 的 System Prompt 新增「指标解读标准」表格（消息比例阈值、响应时间区间、发起/终结模式含义等），LLM 拿到原始数据后自行判断
4. **tools.py 描述更新** — `search_chat_context` 描述改为"返回纯结构化统计指标"
5. **移除图片/OCR 功能** — 删除 `_extract_text_from_image()`、`IMAGE_MIME_TYPES`、`vision_llm`，仅保留 txt/json/md 纯文本上传
6. **前端布局重构** — 结果展示移出双栏布局，独立全宽渲染（居中 1-6-1 列）；仪表盘两列并排；关系进度条四列并排
7. **容器尺寸放大** — 手动输入 110→250px，预览容器 250→350px，expander min-height 400px
8. **移除记忆库 UI** — 删除"存入长期记忆库"checkbox 及相关 session state、状态提示
9. **导入格式指南** — 新增 `docs/如何导入正确格式.md` + 前端内嵌完整格式说明 + 万能 AI 提示词模板
10. **环境变量文档化** — `.env` 加载链（ChatLab/ → portal/ override）在 core_llm.py 中实现

### 2026-07-09 (morning) — Context Engineering + 指数化重构

1. **Schemas 重构** — 删除 `EmotionResponse`/`AtmosphereResponse`，新增 `EmotionIndices`(6项)、`RelationProgress`(4维)、`RelationDynamics`、`ActionSuggestion`
2. **context_engineer.py** — 新建消息预处理 pipeline（排序去重 → 逐轮特征 → 统计摘要 + 互动模式 → Document）
3. **tools.py 重构** — `search_chat_history` → `search_chat_context`(优先搜结构化分析+fallback)，新增 `deep_read_message`
4. **rag_function.py** — 新增 `context_analysis` collection，`save_chats_to_long_term_memory` 自动触发 context engineering
5. **Skill 体系重写** — 三个 Skill 全部输出指数化 JSON；System Prompt 包含完整的分级区间定义
6. **前端指数仪表盘** — 彩色进度条 + 掌控力双色条 + 关系进度条 + 行动建议卡片(emoji分类+优先级星标)

### 2026-06-04

1. 删除冗余文件：`nginx/` `static/` `scripts/` `TODO.md` `course/` `portfolio/`（提升至 portal/）
2. 删除 ChatHistoryAnalyst/.git，统一为 portal/ 大仓 → GitHub [yoiwerr/portal](https://github.com/yoiwerr/portal)
3. `src/main.py` 新增 `/` 首页 + `/css` 静态挂载 + `/chatlab` → localhost:8501 重定向
4. `make dev` 本地一键启动
5. `.env.example` DB_HOST 默认 localhost

### 2026-06-09

1. ChatLab 双栏布局 — 左 2/3（导入+功能），右 1/3（预览面板），水晶卡片阴影，纯白主题
2. CORS + API 修复 — chatlab.js 改用相对路径 `/api/v1`，FastAPI 加 CORS 中间件
3. nginx 路由 — 新增 `/bgm/` `/photo/` location 块
