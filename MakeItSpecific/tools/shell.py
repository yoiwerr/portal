"""
MakeItSpecific Agent Tool — 只读 Shell 预览。

run_shell_preview : 执行白名单只读命令，用于查看项目结构、配置、日志等。
"""

import subprocess
import logging
from pathlib import Path

from langchain_core.tools import tool

logger = logging.getLogger(__name__)

# ── 白名单命令 ──
READONLY_COMMANDS = {
    "ls":       {"args": ["-la", "-lh", "-R"], "max_args": 2, "desc": "列出目录内容"},
    "cat":      {"args": [], "max_args": 1, "desc": "查看文件内容"},
    "head":     {"args": ["-n"], "max_args": 2, "desc": "查看文件前 N 行"},
    "tail":     {"args": ["-n"], "max_args": 2, "desc": "查看文件后 N 行"},
    "wc":       {"args": ["-l", "-w", "-c"], "max_args": 2, "desc": "统计行数/词数/字符数"},
    "tree":     {"args": ["-L", "-d", "-a"], "max_args": 2, "desc": "目录树"},
    "git":      {
        "args": ["log", "status", "branch", "diff", "show"],
        "max_args": 3,
        "desc": "Git 只读操作",
        "subcommands": {
            "log":    {"max_extra": 2, "desc": "提交历史"},
            "status": {"max_extra": 0, "desc": "工作区状态"},
            "branch": {"max_extra": 1, "desc": "分支列表"},
            "diff":   {"max_extra": 2, "desc": "查看差异"},
            "show":   {"max_extra": 1, "desc": "查看提交详情"},
        },
    },
    "du":       {"args": ["-sh", "-h"], "max_args": 2, "desc": "磁盘使用"},
    "find":     {"args": ["-name", "-type"], "max_args": 4, "desc": "查找文件"},
    "file":     {"args": [], "max_args": 1, "desc": "检测文件类型"},
}


def _is_safe_command(cmd: str) -> tuple[bool, str]:
    """
    检查命令是否在安全白名单中。

    Returns:
        (is_safe: bool, reason: str)
    """
    parts = cmd.strip().split()
    if not parts:
        return False, "空命令"

    base = parts[0]

    # 去掉路径前缀 (如 /usr/bin/ls → ls)
    if "/" in base:
        base = base.split("/")[-1]

    if base not in READONLY_COMMANDS:
        return False, f"命令 '{base}' 不在白名单中。可用: {', '.join(READONLY_COMMANDS.keys())}"

    config = READONLY_COMMANDS[base]

    # Git 特殊处理：需要检查子命令
    if base == "git" and len(parts) > 1:
        sub = parts[1]
        allowed_subs = config.get("subcommands", {})
        if sub not in allowed_subs:
            return False, f"git 子命令 '{sub}' 不允许。可用: {', '.join(allowed_subs.keys())}"
        # 检查 git 子命令的参数数量
        max_extra = allowed_subs[sub]["max_extra"]
        extra_args = len(parts) - 2
        if extra_args > max_extra:
            return False, f"git {sub} 参数过多 (最多 {max_extra} 个)"

    else:
        # 普通命令：检查参数数量
        extra_args = len(parts) - 1
        if extra_args > config["max_args"]:
            return False, f"参数过多 (最多 {config['max_args']} 个)"

    # 安全检查：禁止危险选项
    dangerous = {"-rf", "--force", "-f", ">", ">>", "|", ";", "&&", "||", "$(", "`"}
    for part in parts[1:]:
        if part in dangerous:
            return False, f"参数包含危险操作: {part}"

    return True, "OK"


@tool
def run_shell_preview(command: str) -> str:
    """
    【用途】执行白名单只读 Shell 命令，预览项目结构、文件内容、Git 状态等。白名单: ls / cat / head / tail / wc / tree / git(log/status/branch/diff/show) / du / find / file。

    【不要用】
    - 任何需要写入/修改/删除的操作（被安全策略拦截）
    - 不确定命令是否在白名单内时（先列白名单给用户确认）
    - 需要管道、重定向、分号的复合命令（被安全策略拦截）
    - 执行脚本或二进制文件

    【优先级】🟢 低 — 仅在需要查看文件系统状态时使用。大多数信息 LLM 可从对话上下文中推断。

    【参数】command: 单个白名单命令 + 参数，如 "ls -la"、"git diff"、"cat config.py"。
    【限制】超时 10 秒，输出截断至 5000 字符，禁止管道/重定向/分号。
    """
    logger.info(f"[Tool] run_shell_preview: {command}")

    # 安全校验
    is_safe, reason = _is_safe_command(command)
    if not is_safe:
        return f"🛡️ 安全限制: {reason}"

    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=10,
            cwd=None,  # 使用当前工作目录
        )

        output = result.stdout or result.stderr

        if len(output) > 5000:
            output = output[:5000] + "\n... (输出过长，已截断至前 5000 字符)"

        if not output.strip():
            return f"({command} 无输出)"

        return f"### 🔧 {command}\n```\n{output.strip()}\n```"

    except subprocess.TimeoutExpired:
        return f"命令超时 (10秒): {command}"
    except Exception as e:
        return f"执行失败: {str(e)}"
