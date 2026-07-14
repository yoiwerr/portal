# 导出与下载机制

> 信息留存不只是"AI 回复一段 Markdown"——要把生成的内容变成用户可拿走的文件

## 1. 当前状态全景

用户对话中产出的内容，有三条路可以变成持久化资产：

```
用户对话
  │
  ├─ ① add_to_knowledge_base   → PGVector 向量库        → 跨会话语义检索
  ├─ ② write_file              → data/exports/*.md      → 物理文件（无下载入口 ❌）
  └─ ③ export_session_to_md    → data/exports/*.md      → 物理文件（无 API 端点 ❌）
```

| 路径 | 谁触发 | 写到哪 | 用户能拿到吗 |
|------|--------|--------|-------------|
| ① `add_to_knowledge_base` | Agent 在对话中自动/手动调用 | PGVector `domain_knowledge` 表 | ✅ 下次对话 `search_knowledge_base` 可命中 |
| ② `write_file` | Agent 在对话中调用 | `data/exports/*.md` | ❌ 文件落盘但前端没路径，无下载按钮 |
| ③ `export_session_to_md` | 需主动调用 API | `data/exports/*.md` | ❌ 代码已封装但路由器没暴露端点 |

**当前用户体感**：Info Retention Skill 输出一段格式化的 Markdown 文本，显示在聊天气泡里。用户只能看，不能下载。

---

## 2. 三条路的数据流

### 2.1 路径 ① — add_to_knowledge_base（向量库写入）

这是 Agent 在对话过程中**自动触发**的持久化路径。不需要用户主动操作。

```
Agent (Execute 节点)
  │
  ├─ Think: "这段对话有价值，应该记下来"
  ├─ Act: 调用 add_to_knowledge_base(content, title, source)
  │
  ▼
tools/knowledge.py
  │
  ├─ content 校验: ≥30 字符，否则拒绝
  ├─ Embedding: rag.embedding_model.embed_query(content)
  ├─ 写入 PGVector: store.add(collection="domain_knowledge", ...)
  │     ├─ documents: content
  │     ├─ embeddings: [vector]
  │     ├─ metadatas: {source, title, added_at, content_hash, content_length}
  │     └─ ids: md5(source:title:timestamp)[:16]
  │
  └─ 返回 Agent: "✅ 已存入知识库。标题: xxx"
       │
       ▼
  下次对话: search_knowledge_base("相关 query") → PGVector 语义检索 → 命中
```

**关键特性**：
- 同表读写分离：`add_to_knowledge_base` 只写，`search_knowledge_base` 只读
- 无需 reindex：写入后立即可检索（PGVector 事务隔离）
- 有 content_hash 做去重标记（当前未启用自动去重，仅记录）
- 向量检索天然支持模糊语义匹配，不依赖精确关键词

### 2.2 路径 ② — write_file（文件系统写入）

Agent 在对话中**主动或按用户要求**调用 `write_file`，将内容落盘为物理文件。

```
Agent (Execute 节点)
  │
  ├─ Think: "用户让我把这份计划保存下来"
  ├─ Act: 调用 write_file(filename="project_plan.md", content="...", overwrite=false)
  │
  ▼
tools/fs.py
  │
  ├─ 路径校验 (_validate_path):
  │     ├─ 路径穿越拦截: ../ 被拒绝
  │     ├─ 后缀白名单: .md .txt .json .csv .py .html .css .js
  │     └─ 解析到 _write_root (默认 data/exports/)
  │
  ├─ 内容校验:
  │     ├─ 非空
  │     └─ ≤100KB
  │
  ├─ 文件已存在 + overwrite=false → 拒绝 + 提示可设 overwrite=true
  │
  └─ 写入: resolved.parent.mkdir(parents=True, exist_ok=True)
            resolved.write_text(content, encoding="utf-8")
            → 返回 "✅ 文件已写入。路径: /app/data/exports/project_plan.md"
```

**安全边界**：

| 维度 | 限制 |
|------|------|
| 写入目录 | 只能写 `data/exports/`，路径穿越被拦截 |
| 文件类型 | 8 种纯文本后缀白名单 |
| 单文件上限 | 100KB |
| 覆盖保护 | 默认不覆盖，需显式 `overwrite=true` |
| 隐私 | Prompt 禁止写密码/Token（靠模型自觉，无硬拦截） |

### 2.3 路径 ③ — export_session_to_md（完整对话导出）

将整个会话的 user↔assistant 对话历史导出为结构化 Markdown 文件。

```
调用方 (当前没有)
  │
  ▼
agent.export_session(session_id)
  │
  ▼
services/md_export.py :: export_session_to_md()
  │
  ├─ 从 SessionStore 读取完整会话:
  │     ├─ session_store.get_session(session_id)  → 会话元数据
  │     └─ session_store.get_conversation(session_id) → 所有消息
  │
  ├─ 构建 Markdown:
  │     # MakeItSpecific - {title}
  │     > 导出时间 / 模块 / 会话ID
  │     ---
  │     ## 📋 背景信息
  │     ## 💬 对话历史
  │       ### 👤 用户 (timestamp)
  │       ### 🤖 AI (timestamp)
  │
  └─ 写入文件:
        filename = "{title}_{session_id}_{timestamp}.md"
        写入 output_dir (默认 data/exports/)
        返回文件路径
```

**与路径 ② 的区别**：

| 维度 | write_file | export_session_to_md |
|------|-----------|---------------------|
| 触发者 | Agent 在对话中调用 tool | 用户/前端主动调用 API |
| 内容来源 | Agent 生成的结构化文档 | 完整对话历史（user + assistant） |
| 格式 | 取决于 Agent 输出（Markdown/JSON/CSV） | 固定模板：头信息 + 时间线对话 |
| 用途 | 单次产出的文档归档 | 会话级别的完整记录 |

---

## 3. 缺口分析 — 为什么用户拿不到文件

### 缺口 A：write_file 产物无下载入口

```
当前流程:
  Agent 调用 write_file("report.md", content)
    → 文件成功写入 data/exports/report.md
    → Agent 返回文本: "✅ 文件已写入。路径: /app/data/exports/report.md"
    → 用户看到这段文本
    → 用户: "路径在哪儿？我怎么下载？"

应有流程:
  Agent 调用 write_file("report.md", content)
    → 文件写入成功
    → Agent 返回文本 + 前端渲染时识别文件路径
    → 气泡里出现 "📥 下载 report.md" 按钮
    → 用户点击 → GET /api/files/download?path=report.md → 浏览器下载
```

### 缺口 B：export_session_to_md 无 API 端点

`services/md_export.py` 的 `export_session_to_md()` 和 `core/agent.py` 的 `Agent.export_session()` 均已实现，但 `routers/sessions.py` **没有暴露下载端点**。

```
当前 routes/sessions.py:
  GET  /api/sessions          ← ✅ 列表
  GET  /api/sessions/{id}     ← ✅ 详情
  DELETE /api/sessions/{id}   ← ✅ 删除
  GET  /api/sessions/{id}/export  ← ❌ 缺失

app.py 没有挂载 /api/files/ 路由           ← ❌ 缺失
```

---

## 4. 补全方案

### 4.1 新增文件下载路由

在 `routers/` 下新增 `files.py`，提供通用的文件下载能力：

```python
# routers/files.py — 新增
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pathlib import Path

router = APIRouter(prefix="/api/files", tags=["Files"])

@router.get("/download")
async def download_file(path: str):
    """下载 data/exports/ 下的文件。只允许文件名，不允许路径。"""
    filename = Path(path).name  # 剥离路径，防止路径穿越
    file_path = Path("data/exports") / filename

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="文件不存在")
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="不是有效文件")
    if file_path.suffix not in {".md", ".txt", ".json", ".csv", ".html"}:
        raise HTTPException(status_code=403, detail="不支持的文件类型")

    return FileResponse(
        path=str(file_path),
        filename=filename,
        media_type="application/octet-stream",
    )
```

然后在 `app.py` 注册：

```python
from routers import files
app.include_router(files.router)
```

### 4.2 新增会话导出端点

在 `routers/sessions.py` 补充：

```python
from fastapi.responses import FileResponse

@router.get("/{session_id}/export")
async def export_session(session_id: str):
    """导出完整会话为 Markdown 文件并触发下载。"""
    if _agent is None:
        raise HTTPException(status_code=503, detail="Agent 未初始化")

    session = _agent.sessions.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    file_path = _agent.export_session(session_id)
    return FileResponse(
        path=file_path,
        filename=Path(file_path).name,
        media_type="text/markdown; charset=utf-8",
    )
```

### 4.3 前端下载按钮

在 `static/js/chat.js` 的 `finalizeBubble` 中注入下载按钮。判断逻辑：如果 assistant 回复中包含"文件已写入"或明确给出了文件路径，则渲染一个下载按钮。

```javascript
// 在 finalizeBubble 中加:
function finalizeBubble(el, content) {
  el.classList.remove('streaming');
  var contentEl = el.querySelector('.msg-content');
  if (contentEl) {
    contentEl.innerHTML = renderMd(content);
  }

  // 检测文件路径并附加下载按钮
  var fileMatch = content.match(/路径:\s*(.+?\.(md|txt|json|csv|html))/);
  if (fileMatch) {
    var filename = fileMatch[1].split('/').pop();
    var dlBtn = document.createElement('a');
    dlBtn.className = 'download-btn';
    dlBtn.href = 'api/files/download?path=' + encodeURIComponent(filename);
    dlBtn.download = filename;
    dlBtn.textContent = '下载 ' + filename;
    contentEl.appendChild(dlBtn);
  }

  // 原有的反馈按钮...
}
```

---

## 5. 安全模型

```
                        ┌─────────────────────────┐
                        │    用户浏览器            │
                        └───────────┬─────────────┘
                                    │ GET /api/files/download?path=xxx
                                    ▼
                        ┌─────────────────────────┐
                        │   路径剥离 (第一层)      │
                        │   filename = Path(x).name│  ← 去掉所有目录部分
                        └───────────┬─────────────┘
                                    │
                                    ▼
                        ┌─────────────────────────┐
                        │   后缀白名单 (第二层)    │
                        │   .md .txt .json .csv    │  ← 只允许纯文本格式
                        │   .html (拒绝)           │
                        └───────────┬─────────────┘
                                    │
                                    ▼
                        ┌─────────────────────────┐
                        │   文件存在检查 (第三层)  │
                        │   exists? is_file?       │  ← 拒绝目录遍历
                        └───────────┬─────────────┘
                                    │
                                    ▼
                        ┌─────────────────────────┐
                        │   FileResponse          │
                        │   Content-Disposition   │  ← 浏览器下载，不渲染
                        │   attachment            │
                        └─────────────────────────┘
```

三层防御确保：
- **路径穿越**：`Path(user_input).name` 剥离所有 `/` `\` `..`，攻击者传 `../../../etc/passwd` 也只能拿到 `passwd`
- **类型限制**：后缀白名单只允许纯文本，HTML 显式拒绝（防止 XSS）
- **目录限定**：只从 `data/exports/` 读取，且必须是文件不能是目录

---

## 6. 与 info_retention Skill 的配合

Info Retention Skill 是上述机制的主要消费方。一个典型的留存流程：

```
用户: "帮我把刚才的技术选型讨论整理一下，保存下来"

  │
  ▼
Planner: 识别 info_retention 模块 → 提取维度 → 信息完整 → 进入 Execute
  │
  ▼
Execute (ReAct Agent):
  │
  ├─ Think: 需要先回顾对话历史中的决策点
  ├─ Act: search_knowledge_base("技术选型 JSON 解析库 数据库")
  │     → 召回: orjson vs ujson vs rapidjson 的对比结论
  │
  ├─ Think: 知识库有相关背景，整理为结构化文档
  ├─ Output (Markdown):
  │     ### 📌 核心信息
  │     选择了 orjson 作为项目 JSON 解析库...
  │     ### 🔑 关键决策点
  │     1. orjson (✅ 已选) — 性能比 ujson 快 30%...
  │
  ├─ Think: 文档质量不错，用户说了"保存下来"，写入文件
  ├─ Act: write_file(
  │         filename="tech_stack_decisions.md",
  │         content="[完整的 Markdown 文档]",
  │         overwrite=false
  │       )
  │     → ✅ 文件已写入。路径: /app/data/exports/tech_stack_decisions.md
  │
  └─ Think: 这份决策记录也值得存到知识库
      Act: add_to_knowledge_base(
             title="技术选型决策: orjson",
             content="选择了 orjson...原因: 性能比 ujson 快 30%..."
           )
        → ✅ 已存入知识库
```

最终产出：
- **文件**：`data/exports/tech_stack_decisions.md` → 有下载按钮后用户可拿走
- **向量**：PGVector 中一条记录 → 下次对话 `search_knowledge_base` 可命中
- **对话**：SQLite messages 表 → `export_session_to_md` 的原材料

---

## 7. 实施优先级

| 优先级 | 任务 | 改动量 | 影响 |
|--------|------|--------|------|
| **P0** | `routers/files.py` 新增 + `app.py` 注册 | ~30 行 | 打通 write_file → 浏览器下载 |
| **P0** | `routers/sessions.py` 加 `/{id}/export` | ~15 行 | 打通 export_session_to_md → 浏览器下载 |
| **P1** | 前端下载按钮（识别文件路径 + 渲染链接） | ~20 行 JS | 用户可见的下载入口 |
| **P2** | 下载按钮样式（CSS） | ~10 行 | 好看 |

---

## 8. 总结

```
                      ┌─────────────────────────────┐
                      │        对话产出              │
                      └─────────────┬───────────────┘
                                    │
              ┌─────────────────────┼─────────────────────┐
              │                     │                     │
              ▼                     ▼                     ▼
    add_to_knowledge_base    write_file          export_session_to_md
         (向量库)             (文件系统)             (文件系统)
              │                     │                     │
              │                     │                     │
              ▼                     ▼                     ▼
    search_knowledge_base    GET /api/files/      GET /api/sessions/
    下次对话语义检索           download?path=       {id}/export
    ✅ 已可用                 ❌ 待实现             ❌ 待实现
```

三条路各司其职：向量库给 AI 用（语义检索），文件落盘给人用（下载带走），会话导出给归档用（完整记录）。当前只有第一条路通了，后两条路的后台代码已经写完，就差最后一步的 API 端点 + 前端按钮。
