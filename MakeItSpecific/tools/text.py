"""
MakeItSpecific Agent Tools — 文本处理。

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
    【用途】从非结构化文本中自动检测并提取结构化数据。支持 JSON、Markdown 表格、日志条目、键值对四种格式的自动识别。

    【不要用】
    - LLM 自己能一眼看出的简单提取（如 "把这段话里的数字找出来"）
    - 语义理解型提取（如 "提取所有负面评价" — 需要 LLM，规则引擎做不了）
    - 超大文本（> 10K 字符）— 先交给 summarize_text 压缩

    【优先级】🟡 中等 — 规则引擎，确定性高但没有语义理解能力。适用于格式规整的文本。

    【参数】text: 原始文本；format_hint: 期望输出格式 ("json" / "markdown table" / "bullet list")，留空则自动检测。
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
    【用途】逐行对比两段文本/文档/代码，输出行级差异报告 + 相似度统计。

    【不要用】
    - 语义对比（如 "方案A比方案B好在哪"）— 规则引擎只能做字面差异，语义对比交给 LLM
    - 单段文本（需要两段才能对比）
    - 超过 500 行的文本（行级 diff 输出会爆炸）

    【优先级】🟢 低 — 规则引擎行级对比，仅在需要精确字面差异时使用。大多数情况下 LLM 直接对比效果更好。

    【参数】text_a: 第一段文本；text_b: 第二段文本；label_a/label_b: 文本标签 (如 "V1"/"V2" 或 "方案A"/"方案B")。
    【注意】此工具为纯规则引擎，不做语义理解。行号对齐基于简单行序对比，非 LCS 算法。
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
    【用途】对长文本做规则引擎提取摘要。按段落拆分，每段取首句/关键句，拼接为目标长度。

    【不要用】
    - 需要语义理解 / 深层分析的摘要（规则引擎只看位置，不懂内容）— 让 LLM 直接总结
    - 短文本 (≤ max_length) — 不需要摘要
    - 需要保留细节的文档 — 规则摘要会丢失大量信息

    【优先级】🟢 最低 — 本质是文本截断器，非 LLM 级摘要。仅在文本超过上下文窗口限制、需要快速压缩时使用。绝大多数场景下 LLM 直接阅读原文效果更好。

    【参数】text: 要压缩的长文本；max_length: 目标摘要长度（字符数，默认 500）。
    【注意】⚠️ 此工具不调用 LLM，按位置规则提取（首句优先）。信息丢失不可避免，不要假称 "已完整理解"。
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
