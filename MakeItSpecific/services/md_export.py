"""
Markdown 文件导入导出。
- 导出：将完整对话记录输出为 .md 文件
- 导入：读取 .md 文件作为上下文注入
"""

from datetime import datetime
from pathlib import Path
from typing import Optional

from services.session_store import SessionStore


def export_session_to_md(
    session_id: str,
    session_store: SessionStore,
    output_dir: Path,
    title: str = "对话记录"
) -> Path:
    """
    将会话导出为 Markdown 文件。

    Args:
        session_id: 会话 ID
        session_store: 会话存储实例
        output_dir: 输出目录
        title: 导出文件标题

    Returns:
        生成的 .md 文件路径
    """
    session = session_store.get_session(session_id)
    if not session:
        raise ValueError(f"会话不存在: {session_id}")

    messages = session_store.get_conversation(session_id)

    # 构建 Markdown 内容
    lines = [
        f"# MakeItSpecific - {title}",
        "",
        f"> 导出时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"> 模块: {session.get('module', '未知')}",
        f"> 会话ID: {session_id}",
        "",
        "---",
        "",
    ]

    # 背景信息
    if session.get("background"):
        lines.append("## 📋 背景信息")
        lines.append("")
        lines.append(session["background"])
        lines.append("")
        lines.append("---")
        lines.append("")

    # 对话历史
    lines.append("## 💬 对话历史")
    lines.append("")

    role_labels = {
        "user": "👤 用户",
        "assistant": "🤖 AI",
        "system": "⚙ 系统"
    }

    for msg in messages:
        role_label = role_labels.get(msg["role"], msg["role"])
        timestamp = msg.get("created_at", "")[:19] if msg.get("created_at") else ""

        lines.append(f"### {role_label} ({timestamp})")
        lines.append("")
        lines.append(msg["content"])
        lines.append("")

    # 写入文件
    safe_title = "".join(c for c in title if c.isalnum() or c in " _-").strip()
    filename = f"{safe_title}_{session_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    output_path = output_dir / filename

    output_path.write_text("\n".join(lines), encoding="utf-8")
    return output_path


def load_md_file(file_path: Path) -> str:
    """
    读取 .md 文件内容。

    Args:
        file_path: .md 文件路径

    Returns:
        文件的文本内容
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"文件不存在: {file_path}")
    return path.read_text(encoding="utf-8")


def load_multiple_md_files(file_paths: list[Path]) -> str:
    """
    读取多个 .md 文件并合并。

    Args:
        file_paths: .md 文件路径列表

    Returns:
        合并后的文本，每个文件用分隔线隔开
    """
    contents = []
    for fp in file_paths:
        path = Path(fp)
        if path.exists() and path.suffix.lower() == ".md":
            content = path.read_text(encoding="utf-8")
            contents.append(f"## 📄 文件: {path.name}\n\n{content}")

    return "\n\n---\n\n".join(contents)
