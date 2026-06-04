import base64
import json
import os
import re
from typing import List, Optional

from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from langchain_core.messages import HumanMessage

from src.schemas import ImportRequest, AnalysisRequest, ChatMessage, EmotionResponse, AtmosphereResponse, FileUploadResponse
from src.skills.skill01_imitate import execute_imitate_skill
from src.skills.skill02_emotion import execute_emotion_skill
from src.skills.skill03_atmosphere import execute_atmosphere_skill
from src.rag_function import save_chats_to_long_term_memory, import_knowledge_file, list_imported_files, clear_vector_stores
from src.core_llm import vision_llm

app = FastAPI(title="Chat Analysis Agent API", version="1.0")

# 支持的图片 MIME 类型
IMAGE_MIME_TYPES = {"image/png", "image/jpeg", "image/jpg", "image/webp"}


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


async def _extract_text_from_image(image_bytes: bytes, mime_type: str) -> str:
    """使用视觉模型从聊天截图中提取文字内容。"""
    image_b64 = base64.b64encode(image_bytes).decode()
    data_url = f"data:{mime_type};base64,{image_b64}"

    msg = HumanMessage(
        content=[
            {"type": "text",
             "text": (
                 "请提取这张聊天截图中的所有文字对话内容。\n"
                 "要求：\n"
                 "1. 忽略系统时间、电量、信号等 UI 元素\n"
                 "2. 每一行按格式输出：[发送者名称 时间]: 消息内容\n"
                 "3. 不要遗漏任何一条消息\n"
                 "4. 只输出对话，不要任何额外解释"
             )},
            {"type": "image_url", "image_url": {"url": data_url}}
        ]
    )

    response = await vision_llm.ainvoke([msg])
    return response.content
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
    文件上传接口：支持 txt / json / 图片(png/jpg/webp)。
    图片会调用视觉模型提取聊天文字后再解析。
    """
    filename = file.filename or "unknown"
    content_bytes = await file.read()
    mime_type = file.content_type or ""

    if not content_bytes:
        raise HTTPException(status_code=400, detail="上传的文件为空。")

    # --- 分支1: 纯文本 ---
    if filename.endswith(".txt") or mime_type == "text/plain":
        text = content_bytes.decode("utf-8", errors="replace")
        parsed = _parse_text_lines(text)

    # --- 分支2: JSON ---
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

    # --- 分支3: 图片 ---
    elif mime_type in IMAGE_MIME_TYPES or filename.endswith((".png", ".jpg", ".jpeg", ".webp")):
        if not mime_type or mime_type == "application/octet-stream":
            ext_to_mime = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}
            for ext, mt in ext_to_mime.items():
                if filename.lower().endswith(ext):
                    mime_type = mt
                    break
            else:
                mime_type = "image/png"

        try:
            extracted_text = await _extract_text_from_image(content_bytes, mime_type)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"视觉模型提取文字失败: {str(e)}")

        print(f"📷 视觉模型提取的原始文字:\n{extracted_text}")
        parsed = _parse_text_lines(extracted_text)

    else:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件格式。支持: txt, json, png, jpg, webp。收到: {filename} ({mime_type})"
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


@app.post("/api/v1/emotion_analyze", response_model=EmotionResponse, tags=["Skills"])
async def skill_emotion(request: AnalysisRequest):
    """
    Skill 2: 历史情感分析 (强制结构化输出)
    """
    # 直接调用封装好的技能函数
    result = await execute_emotion_skill(request)
    return result

@app.post("/api/v1/analyze_atmosphere", response_model=AtmosphereResponse, tags=["Skills"])
async def skill_atmosphere(request: AnalysisRequest):
    """
    Skill 3: 聊天气氛分析与沟通建议 (Demo版)
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


@app.get("/", response_class=HTMLResponse)
async def homepage():
    """首页"""
    with open(os.path.join(_STATIC_DIR, "index.html"), encoding="utf-8") as f:
        return f.read()


@app.get("/chatlab")
async def chatlab_redirect():
    """本地开发时将 /chatlab 重定向到 Streamlit。服务器上 nginx 会直接拦截。"""
    return RedirectResponse(url="http://localhost:8501")


app.mount("/css", StaticFiles(directory=os.path.join(_STATIC_DIR, "css")), name="css")