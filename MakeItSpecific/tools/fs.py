"""
MakeItSpecific Agent Tool — 文件写入。

write_file : 将内容写入指定目录下的文件。
             限制: 只能写 .md/.txt/.json/.csv/.py/.html/.css/.js。
             路径穿越 (../) 被拦截。默认不覆盖已有文件。
"""

import logging
from pathlib import Path

from langchain_core.tools import tool

logger = logging.getLogger(__name__)

_config = None
_write_root = None

_ALLOWED_SUFFIXES = {".md", ".txt", ".json", ".csv", ".py", ".html", ".css", ".js"}
_MAX_SIZE = 100_000  # 单文件最大 100KB


def set_fs_tool_config(config=None):
    global _config, _write_root
    _config = config
    if config:
        _write_root = getattr(config, "export_dir", None) or (
            config.project_root / "data" / "exports"
        )
    _write_root = Path(_write_root) if _write_root else None


def _validate_path(filename: str) -> tuple[bool, str, Path]:
    """校验写入路径。返回 (ok, reason, resolved_path)。"""
    if _write_root is None:
        return False, "文件写入服务未初始化", None

    path = Path(filename)

    # 路径穿越检测
    try:
        resolved = (_write_root / path).resolve()
        if not str(resolved).startswith(str(_write_root.resolve())):
            return False, f"路径穿越被拦截: {filename}", None
    except Exception:
        return False, f"无效路径: {filename}", None

    # 后缀检测
    if resolved.suffix.lower() not in _ALLOWED_SUFFIXES:
        return False, f"不支持的文件类型 ({resolved.suffix})。允许: {', '.join(sorted(_ALLOWED_SUFFIXES))}", None

    return True, "", resolved


@tool
def write_file(filename: str, content: str, overwrite: bool = False) -> str:
    """
    【用途】将内容写入文件系统。输出目录由服务端配置（默认 data/exports/），Agent 无法写入其他位置。

    【什么时候用】
    - info_retention 整理完文档后落盘（「把这篇整理好的文档保存为 .md」）
    - work_arranger 产出项目计划后导出为 .md 或 .json
    - 用户明确要求「帮我把这个保存到文件」
    - 对话中产出了值得版本控制的内容（代码片段、配置模板）

    【坚决不用】
    - 写入系统文件/配置文件 — 被路径穿越检测拦截
    - 写入二进制文件 — 只支持 .md/.txt/.json/.csv/.py/.html/.css/.js
    - 覆盖已有文件（除非 overwrite=True）
    - 超过 100KB 的内容
    - 隐私信息、密码、Token 等 — 永远不落盘

    【与其他 tool 的关系】
    - 与 add_to_knowledge_base: add_to_kb 写 PGVector（向量检索），write_file 写文件系统（直接读取）。
      不同存储后端，不同用途 — 知识库 vs 文档归档。无重叠。
    - 与 run_shell_preview: 互补。shell 只读文件，write_file 只写不读。
    - 与 python_exec: 无关。python_exec 不能做文件 IO。

    【参数】
    - filename: 文件名或相对路径（如 "project_plan.md" 或 "exports/report.json"）
    - content:  文件内容（纯文本/Markdown/JSON/CSV）
    - overwrite: 是否覆盖已有文件（默认 false — 安全保护）

    【返回】写入结果。成功返回文件完整路径。
    """
    ok, reason, resolved = _validate_path(filename)
    if not ok:
        logger.warning(f"[Tool] write_file 拒绝: {reason}")
        return f"🛡️ {reason}"

    if not content or not content.strip():
        return "内容为空，拒绝写入。"

    if len(content) > _MAX_SIZE:
        return f"内容过大 ({len(content)} 字符 > {_MAX_SIZE})，拒绝写入。"

    if resolved.exists() and not overwrite:
        return (
            f"文件已存在: {resolved}\n"
            f"如需覆盖，请设置 overwrite=true。"
        )

    try:
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(content, encoding="utf-8")
        logger.info(f"[Tool] write_file: {resolved} ({len(content)} 字符)")

        return (
            f"✅ 文件已写入。\n"
            f"- 路径: {resolved}\n"
            f"- 大小: {len(content)} 字符\n"
        )
    except Exception as e:
        logger.error(f"[Tool] write_file 失败: {e}")
        return f"文件写入失败: {str(e)}"
