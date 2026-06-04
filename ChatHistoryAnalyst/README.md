# ChatLab — 聊天记录分析引擎

基于 AI Agent 的聊天记录深度分析工具，支持情感分析、语气模仿与沟通气氛评估。

## 功能

- **数据导入** — 支持 TXT / JSON / 聊天截图（PNG/JPG/WebP），截图自动 OCR 提取文字
- **语气模仿** — 模仿目标人物的说话风格和用词习惯，预测其下一条回复
- **情感分析** — 分析对方的情感状态，输出情感得分、主导情绪及分析依据
- **气氛分析** — 评估对话的权力动态、沟通姿态，给出可执行的沟通建议
- **长期记忆** — 聊天记录存入 PostgreSQL + pgvector 向量库，支持 RAG 检索

## 技术栈

| 层级 | 技术 |
|------|------|
| 后端框架 | FastAPI + Uvicorn |
| 前端 | Streamlit |
| AI 模型 | 通义千问 (DashScope) — qwen3-max / qwen3-omni-flash |
| Agent 框架 | LangChain / LangGraph |
| 向量存储 | PostgreSQL + pgvector (PGVector) |
| Embedding | DashScope Embeddings (qwen3-rerank) |
| 联网搜索 | Tavily Search |
| 可观测 | LangSmith |

## 快速开始

### 环境要求

- Python >= 3.12
- PostgreSQL 数据库（需安装 pgvector 扩展）

### 安装

```bash
# 克隆项目
git clone <repo-url>
cd ChatHistoryAnalyst

# 创建虚拟环境并安装依赖
uv sync
```

### 配置

复制环境变量模板并填写实际值：

```bash
cp .env.example .env
```

编辑 `.env` 文件，填入你的 API Key 和数据库连接信息。

### 启动 PostgreSQL

确保 PostgreSQL 已安装 pgvector 扩展，并创建数据库：

```sql
CREATE DATABASE chatdemopg;
CREATE EXTENSION IF NOT EXISTS vector;
```

### 导入知识库资料

```bash
python import_knowledge.py
```

### 启动服务

```bash
# 终端 1：启动后端 API
uvicorn src.main:app --reload

# 终端 2：启动前端界面
streamlit run front/frontend.py
```

然后访问 `http://localhost:8501` 即可使用。

## API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/upload_chat_file` | 上传聊天文件（截图/文本/JSON） |
| POST | `/api/v1/import_chat` | 直接提交解析后的聊天数据 |
| POST | `/api/v1/imitate` | 模仿目标人物回复 |
| POST | `/api/v1/emotion_analyze` | 情感状态分析 |
| POST | `/api/v1/analyze_atmosphere` | 沟通气氛与权力动态分析 |
| POST | `/api/v1/add_memory` | 将聊天记录存入向量库 |
| POST | `/api/v1/import_knowledge` | 导入心理学参考资料 |
| GET  | `/api/v1/imported_files` | 查看已导入的知识文件 |

## 项目结构

```
ChatHistoryAnalyst/
├── src/
│   ├── main.py              # FastAPI 应用入口
│   ├── core_llm.py           # LLM 模型配置
│   ├── schemas.py            # Pydantic 数据模型
│   ├── tools.py              # Agent 工具定义（知识库/历史/联网搜索）
│   ├── rag_function.py       # RAG 向量库操作
│   └── skills/
│       ├── skill01_imitate.py    # 语气模仿
│       ├── skill02_emotion.py    # 情感分析
│       └── skill03_atmosphere.py # 气氛分析
├── front/
│   └── frontend.py          # Streamlit 前端界面
├── data/                    # 心理学参考资料 (txt)
├── config/                  # 配置文件
├── import_knowledge.py      # 知识库导入脚本
└── pyproject.toml
```
