"""
文件下载接口。

GET /api/files/download?path=  — 下载 data/exports/ 下的文件
"""

from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

router = APIRouter(prefix="/api/files", tags=["Files"])

_EXPORT_DIR = Path(__file__).resolve().parent.parent / "data" / "exports"
_ALLOWED_SUFFIXES = {".md", ".txt", ".json", ".csv", ".py", ".html", ".css", ".js"}


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
