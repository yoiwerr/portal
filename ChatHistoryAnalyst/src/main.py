import json
import os
import re
from typing import List

from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from src.schemas import ImportRequest, AnalysisRequest, ChatMessage, EmotionIndices, RelationDynamics, FileUploadResponse
from src.skills.skill01_imitate import execute_imitate_skill
from src.skills.skill02_emotion import execute_emotion_skill
from src.skills.skill03_atmosphere import execute_atmosphere_skill
from src.rag_function import save_chats_to_long_term_memory, import_knowledge_file, list_imported_files, clear_vector_stores

app = FastAPI(title="Chat Analysis Agent API", version="1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 支持的聊天记录格式说明
CHAT_FORMAT_HELP = (
    "支持的格式：\n"
    "1. 纯文本格式 (.txt / .md) — 每行: [发送者 时间]: 消息内容\n"
    "   示例: [张三 2024-06-01 10:30]: 你好，今天有空吗？\n"
    "2. JSON 格式 (.json) — 数组: [{{\"sender\": \"...\", \"timestamp\": \"...\", \"content\": \"...\"}}, ...]"
)


def _parse_text_lines(text: str) -> List[ChatMessage]:
    """将文本按 [发送者 时间]: 内容 格式解析为 ChatMessage 列表。"""
    pattern = r"\[(.*?)\s+(.*?)\][:：]\s*(.*)"
    parsed: List[ChatMessage] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        match = re.match(pattern, line)
        if match:
            sender, time, content = match.groups()
            parsed.append(ChatMessage(sender=sender, timestamp=time, content=content))
        else:
            print(f"Warning: 无法解析文本行 -> {line}")
    return parsed
@app.post("/api/v1/import_chat", tags=["Data Processing"])
async def import_chat_data(request: ImportRequest):
    """
    数据接入层：解析聊天记录并自动存入 RAG 向量库。
    """
    parsed_chats: List[ChatMessage] = []

    if request.format_type == "json" and request.json_data:
        try:
            for item in request.json_data:
                parsed_chats.append(ChatMessage(
                    sender=item.get("sender", "Unknown"),
                    content=item.get("content", ""),
                    timestamp=item.get("timestamp", "Unknown")
                ))
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"JSON 解析失败: {str(e)}")

    elif request.format_type == "text" and request.text_data:
        parsed_chats = _parse_text_lines(request.text_data)
    else:
        raise HTTPException(status_code=400, detail="缺少数据，或者 format_type 未知。")

    rag_message = ""
    if parsed_chats and request.save_to_rag:
        try:
            rag_message = save_chats_to_long_term_memory(
                recent_chats=parsed_chats,
                target_person=request.target_person
            )
        except Exception as e:
            print(f"RAG 写入失败: {e}")

    return {
        "status": "success",
        "message": f"成功导入 {len(parsed_chats)} 条聊天记录。{rag_message}",
        "data": parsed_chats
    }


@app.post("/api/v1/upload_chat_file", response_model=FileUploadResponse, tags=["Data Processing"])
async def upload_chat_file(
    file: UploadFile = File(...),
    target_person: str = Form(default="Unknown"),
    save_to_rag: bool = Form(default=False),
):
    """
    文件上传接口：支持 txt / json / md 格式。
    文本格式: [发送者 时间]: 消息内容
    JSON 格式: [{"sender": "...", "timestamp": "...", "content": "..."}, ...]
    """
    filename = file.filename or "unknown"
    content_bytes = await file.read()
    mime_type = file.content_type or ""

    if not content_bytes:
        raise HTTPException(status_code=400, detail="上传的文件为空。")

    # ── 分支1: 纯文本（包含 .txt / .md / .text）──
    if filename.endswith((".txt", ".md", ".text")) or mime_type == "text/plain":
        text = content_bytes.decode("utf-8", errors="replace")
        parsed = _parse_text_lines(text)

    # ── 分支2: JSON ──
    elif filename.endswith(".json") or mime_type == "application/json":
        try:
            raw = json.loads(content_bytes.decode("utf-8"))
        except json.JSONDecodeError as e:
            raise HTTPException(status_code=400, detail=f"JSON 解析失败: {str(e)}")
        if not isinstance(raw, list):
            raise HTTPException(status_code=400, detail="JSON 文件必须是数组格式 [{sender, content, timestamp}, ...]")
        parsed = []
        for item in raw:
            parsed.append(ChatMessage(
                sender=item.get("sender", "Unknown"),
                content=item.get("content", ""),
                timestamp=item.get("timestamp", "Unknown"),
            ))

    else:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件格式。仅支持 txt、json、md 纯文本格式。收到: {filename} ({mime_type})\n{CHAT_FORMAT_HELP}"
        )

    if not parsed:
        raise HTTPException(status_code=400, detail="未能从文件中解析出任何聊天记录，请检查文件内容或格式。")

    rag_message = ""
    if save_to_rag:
        try:
            rag_message = save_chats_to_long_term_memory(
                recent_chats=parsed,
                target_person=target_person,
            )
        except Exception as e:
            print(f"RAG 写入失败: {e}")

    return FileUploadResponse(
        status="success",
        message=f"成功解析 {len(parsed)} 条聊天记录。{rag_message}",
        parsed_chats=parsed,
    )


@app.post("/api/v1/imitate", tags=["Skills"])
async def skill_imitate(request: AnalysisRequest):
    """
    Skill 1: 模仿聊天对象对话
    所有的核心业务逻辑均已解耦至 src/skills/skill_1_imitate.py
    """
    # 直接调用封装好的技能函数
    result = await execute_imitate_skill(request)
    return result


@app.post("/api/v1/emotion_analyze", response_model=EmotionIndices, tags=["Skills"])
async def skill_emotion(request: AnalysisRequest):
    """
    Skill 2: 情感心理指数分析 — 输出真诚指数、回避指数、冷暴力指数、情绪稳定性、主导情绪、情感趋势
    """
    # 直接调用封装好的技能函数
    result = await execute_emotion_skill(request)
    return result

@app.post("/api/v1/analyze_atmosphere", response_model=RelationDynamics, tags=["Skills"])
async def skill_atmosphere(request: AnalysisRequest):
    """
    Skill 3: 关系动力学分析 — 输出掌控力分配、关系进度条(4维)、沟通姿态诊断、行动建议卡片
    """
    result = await execute_atmosphere_skill(request)
    return result


@app.post("/api/v1/add_memory", tags=["Memory Management"])
async def add_chat_memory(request: AnalysisRequest):
    """
    数据沉淀接口：将前端的聊天记录写入 PostgreSQL 向量库，形成长期记忆。
    """
    try:
        # 调用 rag_function.py 中的核心逻辑
        result_message = save_chats_to_long_term_memory(
            recent_chats=request.recent_chat,
            target_person=request.target_person
        )
        return {
            "status": "success",
            "message": result_message
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"保存记忆失败: {str(e)}")

@app.post("/api/v1/import_knowledge", tags=["Data Processing"])
async def import_knowledge(file_name: str):
    """
    内部接口：将 data/ 目录下的心理学参考资料 txt 导入知识库。
    调用示例: POST /api/v1/import_knowledge?file_name=DBL.txt
    每个文件只需导入一次，重复调用会自动跳过。
    """
    result = import_knowledge_file(file_name)
    return {"status": "success", "message": result}


@app.get("/api/v1/imported_files", tags=["Data Processing"])
async def get_imported_files():
    """查看已导入知识库的文件列表。"""
    files = list_imported_files()
    return {"status": "success", "imported_files": files}


@app.get("/api/health", tags=["System"])
async def health_check():
    """健康检查 — nginx / update.sh 用"""
    return {"status": "ok"}


@app.delete("/api/v1/clear_vector_store", tags=["Memory Management"])
async def clear_vector_store_endpoint():
    """
    清理所有向量表（langchain_pg_embedding + langchain_pg_collection）。
    用于向量维度变更后重建，调用后需重新导入知识文件和聊天记录。
    """
    result = clear_vector_stores()
    return {"status": "success", "message": result}


# ── Homepage (local dev) ─────────────────────────────

_STATIC_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "static")
_IS_DOCKER = not os.path.isdir(_STATIC_DIR)  # Docker 中 nginx 提供静态文件


if not _IS_DOCKER:
    @app.get("/", response_class=HTMLResponse)
    async def homepage():
        """首页"""
        with open(os.path.join(_STATIC_DIR, "index.html"), encoding="utf-8") as f:
            return f.read()


    @app.get("/chatlab", response_class=HTMLResponse)
    async def chatlab_page():
        """ChatLab 前端页面"""
        with open(os.path.join(_STATIC_DIR, "chatlab.html"), encoding="utf-8") as f:
            return f.read()


    @app.get("/specific")
    async def specific_redirect():
        """MakeItSpecific — 本地开发时重定向到 :8001"""
        return RedirectResponse(url="http://localhost:8001")


    app.mount("/css", StaticFiles(directory=os.path.join(_STATIC_DIR, "css")), name="css")
    app.mount("/js", StaticFiles(directory=os.path.join(_STATIC_DIR, "js")), name="js")
    app.mount("/bgm", StaticFiles(directory=os.path.join(_STATIC_DIR, "bgm")), name="bgm")
    app.mount("/photo", StaticFiles(directory=os.path.join(_STATIC_DIR, "photo")), name="photo")