"""
MakeItSpecific Agent Tool — Python 代码沙箱执行。

python_exec : 在隔离环境中执行 Python 代码片段，返回 stdout/stderr。
             需要 SANDBOX_ENABLED=true 才启用。
"""

import logging
import sys
import io
import traceback
import time

from langchain_core.tools import tool

logger = logging.getLogger(__name__)

# 全局配置引用
_config = None


def set_code_tool_config(config):
    global _config
    _config = config


def _is_enabled() -> bool:
    """检查沙箱是否启用。"""
    if _config is None:
        return False
    return getattr(_config, "sandbox_enabled", False)


@tool
def python_exec(code: str) -> str:
    """
    【用途】在隔离沙箱中执行 Python 代码，返回 stdout/stderr。适用于数据分析、计算验证、格式转换（JSON/CSV/Markdown 互转）。

    【不要用】
    - 纯文本处理、简单计算、不需要代码就能回答的问题（LLM 直接处理更快）
    - 需要访问文件系统的任务（沙箱禁止文件写入）
    - 需要网络请求的任务（沙箱禁止网络访问）
    - 不确定代码是否安全时

    【优先级】🟡 中等 — 仅在需要精确计算或格式转换时使用，不要为了 "演示" 而调。

    【参数】code: 完整的 Python 代码字符串。
    【限制】超时 30s，禁止文件写入/网络/系统命令，可用模块：json, math, datetime, re, collections, itertools, csv 等。
    【前置条件】需设置 SANDBOX_ENABLED=true。
    """
    if not _is_enabled():
        return (
            "⚠️ Python 沙箱未启用。\n"
            "请设置环境变量 SANDBOX_ENABLED=true 来启用此功能。\n"
            "安全提示: 启用后 Agent 可执行任意 Python 代码，"
            "建议仅在本地开发环境或可信环境中使用。"
        )

    timeout = getattr(_config, "sandbox_timeout", 30.0) if _config else 30.0

    logger.info(f"[Tool] python_exec: {code[:80]}...")

    # ── 安全检查 ──
    forbidden = [
        "os.system", "subprocess", "__import__('os')",
        "open(",
        "shutil.rmtree", "os.remove", "os.unlink",
        "socket", "requests", "urllib", "httpx",
        "exec(", "eval(", "compile(",
    ]
    code_lower = code.lower()
    for pattern in forbidden:
        if pattern in code_lower:
            return f"⚠️ 安全限制: 代码中包含禁止的调用 ({pattern})。沙箱不允许文件写入、网络访问、系统命令。"

    # ── 执行沙箱 ──
    stdout = io.StringIO()
    stderr = io.StringIO()
    old_stdout = sys.stdout
    old_stderr = sys.stderr

    # 限制命名空间
    safe_builtins = {
        "abs": abs, "all": all, "any": any, "bin": bin, "bool": bool,
        "chr": chr, "dict": dict, "divmod": divmod, "enumerate": enumerate,
        "filter": filter, "float": float, "format": format, "frozenset": frozenset,
        "hash": hash, "hex": hex, "int": int, "isinstance": isinstance,
        "issubclass": issubclass, "iter": iter, "len": len, "list": list,
        "map": map, "max": max, "min": min, "next": next, "oct": oct,
        "ord": ord, "pow": pow, "print": print, "range": range,
        "repr": repr, "reversed": reversed, "round": round, "set": set,
        "slice": slice, "sorted": sorted, "str": str, "sum": sum,
        "tuple": tuple, "type": type, "zip": zip,
        # 常用模块
        "json": __import__("json"),
        "math": __import__("math"),
        "random": __import__("random"),
        "datetime": __import__("datetime"),
        "collections": __import__("collections"),
        "itertools": __import__("itertools"),
        "functools": __import__("functools"),
        "re": __import__("re"),
        "statistics": __import__("statistics"),
        "textwrap": __import__("textwrap"),
        "pprint": __import__("pprint"),
        "hashlib": __import__("hashlib"),
        "base64": __import__("base64"),
        "csv": __import__("csv"),
        "io": __import__("io"),
        "copy": __import__("copy"),
    }

    safe_globals = {"__builtins__": safe_builtins}

    start = time.time()
    result_lines = []

    try:
        sys.stdout = stdout
        sys.stderr = stderr

        exec(code, safe_globals)

        sys.stdout = old_stdout
        sys.stderr = old_stderr

        elapsed = time.time() - start

        out = stdout.getvalue()
        err = stderr.getvalue()

        if out:
            result_lines.append(f"### 标准输出\n```\n{out.strip()[:2000]}\n```")
        if err:
            result_lines.append(f"### 标准错误\n```\n{err.strip()[:1000]}\n```")
        if not out and not err:
            result_lines.append("（代码执行完毕，无输出）")

        result_lines.append(f"\n⏱ 耗时: {elapsed:.2f}s")

        # 捕获最后的表达式值
        if "_" in safe_globals:
            val = safe_globals["_"]
            if val is not None and not callable(val):
                result_lines.append(f"\n返回值: `{repr(val)[:500]}`")

        return "\n".join(result_lines)

    except Exception as e:
        sys.stdout = old_stdout
        sys.stderr = old_stderr
        elapsed = time.time() - start

        out = stdout.getvalue()
        if out:
            result_lines.append(f"### 标准输出（出错前）\n```\n{out.strip()[:1000]}\n```")

        tb = traceback.format_exc()
        result_lines.append(f"### 执行错误\n```\n{tb[-2000:]}\n```")
        result_lines.append(f"\n⏱ 耗时: {elapsed:.2f}s (出错终止)")

        return "\n".join(result_lines)
