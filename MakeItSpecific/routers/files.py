"""
文件上传/下载接口。

GET  /api/files/download?path=  — 下载 data/exports/ 下的文件
POST /api/files/save             — 保存 Markdown 内容并返回下载 URL
"""

import re
from pathlib import Path
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from models.schemas import SaveMarkdownRequest, SaveMarkdownResponse

router = APIRouter(prefix="/api/files", tags=["Files"])

_EXPORT_DIR = Path(__file__).resolve().parent.parent / "data" / "exports"
_ALLOWED_SUFFIXES = {".md", ".txt", ".json", ".csv", ".py", ".html", ".css", ".js"}


def _safe_filename(title: str) -> str:
    """从标题生成安全文件名：只保留中英文/数字/下划线/连字符，最多 40 字符。"""
    # 保留：中文(一-鿿)、英文、数字、_、-
    safe = re.sub(r'[^一-鿿\w\-]', '_', title)
    safe = re.sub(r'_+', '_', safe)  # 合并连续下划线
    safe = safe.strip('_') or 'untitled'
    return safe[:40]


@router.get("/download")
async def download_file(path: str = Query(..., description="文件名（不支持路径，自动剥离目录）")):
    """
    下载 data/exports/ 下的文件。

    安全措施（三层）：
    1. 路径剥离 — 只取文件名，拒绝 ../ 路径穿越
    2. 后缀白名单 — 只允许纯文本格式，拒绝 HTML 防止 XSS
    3. 文件校验 — 拒绝目录 / 不存在 / 非文件
    """
    # 第 1 层：剥离路径，拒绝路径穿越
    filename = Path(path).name
    if not filename or filename != path.split("/")[-1].split("\\")[-1]:
        raise HTTPException(status_code=400, detail="无效的文件名")

    file_path = _EXPORT_DIR / filename

    # 第 2 层：后缀白名单
    if file_path.suffix.lower() not in _ALLOWED_SUFFIXES:
        raise HTTPException(
            status_code=403,
            detail=f"不支持的文件类型 ({file_path.suffix})。允许: {', '.join(sorted(_ALLOWED_SUFFIXES))}",
        )

    # 第 3 层：存在性 + 类型校验
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="文件不存在")
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="不是有效文件")

    return FileResponse(
        path=str(file_path.resolve()),
        filename=filename,
        media_type="application/octet-stream",
    )


@router.post("/save", response_model=SaveMarkdownResponse)
async def save_markdown(req: SaveMarkdownRequest):
    """
    保存 Markdown 内容到 data/exports/，返回下载 URL。

    用于：
    - 前端 "下载 .md" 按钮（客户端 Blob 足够，此端点供工具侧使用）
    - export_markdown 工具调用
    - 外部脚本批量生成文档
    """
    if not req.content or len(req.content.strip()) < 10:
        raise HTTPException(status_code=400, detail="内容过短（至少 10 字符）")

    _EXPORT_DIR.mkdir(parents=True, exist_ok=True)

    safe_title = _safe_filename(req.title)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{safe_title}_{ts}.md"
    filepath = _EXPORT_DIR / filename

    filepath.write_text(req.content, encoding="utf-8")

    download_url = f"/api/files/download?path={filename}"

    return SaveMarkdownResponse(
        filename=filename,
        download_url=download_url,
    )
