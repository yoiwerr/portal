"""
MakeItSmooth Agent Tools — 文本处理。

parse_text     : 从非结构化文本提取结构化数据（JSON/表格/列表）
compare_texts  : 对比两段文本，输出差异报告
summarize_text : 对长文本分段摘要
"""

import json
import logging
import re

from langchain_core.tools import tool

logger = logging.getLogger(__name__)

# 模型引用（依赖注入）
_model = None


def set_text_tool_model(model):
    global _model
    _model = model


# ============================================================
# Tool: 结构化提取
# ============================================================

@tool
def parse_text(text: str, format_hint: str = "") -> str:
    """
    从非结构化文本中提取结构化信息。

    适用场景:
    - 用户粘贴了一段日志/报错信息 → 提取关键字段
    - 用户给了一段需求描述 → 提取为 JSON 格式
    - 用户给了表格数据 → 格式化为 Markdown 表格

    参数:
    - text: 要解析的原始文本
    - format_hint: 期望的输出格式（如 "json"、"markdown table"、"bullet list"）
    """
    logger.info(f"[Tool] parse_text: {len(text)} chars, hint={format_hint}")

    lines = [f"### 解析结果 ({len(text)} 字符)\n"]

    # ── 自动检测 ──
    detected = _detect_structure(text)

    # ── 按类型解析 ──
    if "json" in format_hint.lower() or detected == "json_like":
        extracted = _extract_json_like(text)
        lines.append("**类型**: JSON\n")
        lines.append(f"```json\n{json.dumps(extracted, ensure_ascii=False, indent=2)}\n```")

    elif "table" in format_hint.lower() or detected == "tabular":
        rows = _extract_tabular(text)
        lines.append("**类型**: 表格\n")
        if rows:
            lines.append(_to_markdown_table(rows))
        else:
            lines.append("（未能识别表格结构）")

    elif detected == "log":
        entries = _extract_log_entries(text)
        lines.append(f"**类型**: 日志 ({len(entries)} 条)\n")
        for entry in entries[:20]:
            lines.append(f"- `{entry[:120]}`")

    elif detected == "key_value":
        pairs = _extract_key_value_pairs(text)
        lines.append("**类型**: 键值对\n")
        for k, v in pairs.items():
            lines.append(f"- **{k}**: {v}")

    else:
        # 通用提取: 统计信息 + 关键片段
        lines.append("**类型**: 通用文本\n")
        lines.append(f"- 字符数: {len(text)}")
        lines.append(f"- 行数: {text.count(chr(10)) + 1}")
        lines.append(f"- 估算词数: {len(text.split())}")

        # 提取链接
        urls = re.findall(r'https?://[^\s<>"]+', text)
        if urls:
            lines.append(f"- 链接: {len(urls)} 个")
            for u in urls[:5]:
                lines.append(f"  - {u}")

        # 提取代码块
        code_blocks = re.findall(r'```[\s\S]*?```', text)
        if code_blocks:
            lines.append(f"- 代码块: {len(code_blocks)} 个")

    return "\n".join(lines)


# ============================================================
# Tool: 文本对比
# ============================================================

@tool
def compare_texts(text_a: str, text_b: str, label_a: str = "A", label_b: str = "B") -> str:
    """
    对比两段文本（或两个版本的文档/代码），输出差异报告。

    适用场景:
    - 对比两个技术方案的优劣
    - 对比修改前后的提示词版本
    - 对比两个调研结论的一致性

    参数:
    - text_a: 第一段文本
    - text_b: 第二段文本
    - label_a: 文本 A 的标签（如 "方案A"、"V1"）
    - label_b: 文本 B 的标签
    """
    logger.info(f"[Tool] compare_texts: A={len(text_a)} chars, B={len(text_b)} chars")

    lines_a = text_a.split("\n")
    lines_b = text_b.split("\n")

    # ── 行级 diff ──
    added = []
    removed = []
    common = 0

    max_len = max(len(lines_a), len(lines_b))
    for i in range(max_len):
        a = lines_a[i].strip() if i < len(lines_a) else None
        b = lines_b[i].strip() if i < len(lines_b) else None

        if a is None:
            added.append((i + 1, b))
        elif b is None:
            removed.append((i + 1, a))
        elif a == b:
            common += 1
        else:
            removed.append((i + 1, a))
            added.append((i + 1, b))

    # ── 统计 ──
    total = max_len
    similarity = common / total if total > 0 else 0
    total_changed = len(added) + len(removed)

    report = [
        f"### 文本对比: {label_a} ↔ {label_b}",
        "",
        f"| 指标 | 值 |",
        f"|------|-----|",
        f"| {label_a} 行数 | {len(lines_a)} |",
        f"| {label_b} 行数 | {len(lines_b)} |",
        f"| 相同行 | {common} |",
        f"| 变更行 | {total_changed} |",
        f"| 相似度 | {similarity:.0%} |",
        "",
    ]

    if removed:
        report.append(f"### ➖ 仅 {label_a} 中有 ({len(removed)} 行)\n")
        for lineno, line in removed[:10]:
            report.append(f"- L{lineno}: {line[:120]}")
        if len(removed) > 10:
            report.append(f"  ... 还有 {len(removed) - 10} 行")

    if added:
        report.append(f"\n### ➕ 仅 {label_b} 中有 ({len(added)} 行)\n")
        for lineno, line in added[:10]:
            report.append(f"- L{lineno}: {line[:120]}")
        if len(added) > 10:
            report.append(f"  ... 还有 {len(added) - 10} 行")

    return "\n".join(report)


# ============================================================
# Tool: 文本摘要
# ============================================================

@tool
def summarize_text(text: str, max_length: int = 500) -> str:
    """
    对长文本进行分段摘要。用于处理超长文档、文章、或对话历史。

    注意: 此工具使用规则提取（不调用 LLM），如需 LLM 级摘要请
    让 Agent 直接阅读文本后用自然语言总结。

    参数:
    - text: 要摘要的文本
    - max_length: 摘要目标长度（字符数），默认 500
    """
    logger.info(f"[Tool] summarize_text: {len(text)} chars → target {max_length}")

    if len(text) <= max_length:
        return text

    # ── 规则提取: 取每个段落的首句 + 关键位置 ──
    paragraphs = re.split(r'\n\s*\n', text)

    if len(paragraphs) <= 3:
        # 短文档: 取开头 + 结尾
        head = text[:max_length // 2]
        tail = text[-(max_length // 2):]
        return f"{head}\n\n...（省略 {len(text) - max_length} 字符）...\n\n{tail}"

    # 多段落文档: 每段取首句
    summary_parts = []
    budget = max_length // len(paragraphs)

    for i, para in enumerate(paragraphs):
        para = para.strip()
        if not para:
            continue
        # 取每段前 N 字符
        if len(para) > budget:
            # 尽量在句号处截断
            sentences = re.split(r'(?<=[。！？.!?])\s*', para)
            snippet = ""
            for s in sentences:
                if len(snippet) + len(s) <= budget:
                    snippet += s
                else:
                    break
            summary_parts.append(snippet or para[:budget])
        else:
            summary_parts.append(para)

    summary = "\n\n".join(summary_parts)

    if len(summary) > max_length:
        summary = summary[:max_length] + "\n\n..."

    return f"### 文本摘要 (原始: {len(text)} 字符 → 摘要: {len(summary)} 字符)\n\n{summary}"


# ============================================================
# 内部: 文本结构检测
# ============================================================

def _detect_structure(text: str) -> str:
    """自动检测文本的结构类型。"""
    text_stripped = text.strip()

    # JSON
    if text_stripped.startswith("{") and text_stripped.endswith("}"):
        return "json_like"
    if text_stripped.startswith("[") and text_stripped.endswith("]"):
        return "json_like"

    # 表格: 有 | 分隔的多行
    lines = text_stripped.split("\n")
    bar_lines = sum(1 for l in lines if l.strip().startswith("|"))
    if bar_lines >= 3:
        return "tabular"

    # 日志: 有时间戳模式
    log_pattern = r'\d{4}[-/]\d{2}[-/]\d{2}\s+\d{2}:\d{2}:\d{2}'
    if re.search(log_pattern, text):
        return "log"

    # 键值对: key: value 或 key=value 模式密集
    kv_lines = sum(1 for l in lines if re.match(r'^[\w_-]+\s*[:=]\s*\S', l.strip()))
    if kv_lines >= len(lines) * 0.5:
        return "key_value"

    return "plain"


def _extract_json_like(text: str) -> dict:
    """尝试从文本中提取 JSON。"""
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        pass
    # 尝试提取 {...} 块
    match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except (json.JSONDecodeError, ValueError):
            pass
    return {"_raw": text[:500], "_parse_error": "无法解析为 JSON"}


def _extract_tabular(text: str) -> list:
    """从 Markdown 表格中提取行数据。"""
    rows = []
    for line in text.strip().split("\n"):
        line = line.strip()
        if line.startswith("|") and line.endswith("|"):
            cells = [c.strip() for c in line[1:-1].split("|")]
            if not all(c.startswith("---") for c in cells):
                rows.append(cells)
    return rows


def _to_markdown_table(rows: list) -> str:
    if not rows:
        return "（空表格）"
    md = "| " + " | ".join(rows[0]) + " |\n"
    md += "|" + "|".join(["---" for _ in rows[0]]) + "|\n"
    for row in rows[1:]:
        md += "| " + " | ".join(row) + " |\n"
    return md


def _extract_log_entries(text: str) -> list:
    """提取日志中的关键条目。"""
    return [l.strip() for l in text.split("\n")
            if re.search(r'(ERROR|WARN|FATAL|CRITICAL|Exception|Traceback|fail)', l, re.IGNORECASE)]


def _extract_key_value_pairs(text: str) -> dict:
    """提取键值对。"""
    pairs = {}
    for line in text.strip().split("\n"):
        match = re.match(r'^[\s]*([\w_-]+)\s*[:=]\s*(.+)$', line.strip())
        if match:
            pairs[match.group(1)] = match.group(2).strip()
    return pairs
