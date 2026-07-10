# src/context_engineer.py
"""
Context Engineering 层 — 将原始聊天记录预处理为结构化统计数据。

原则：代码只做数据计算和格式化，不做语义解读。
      所有"这意味着什么"的判断交给 LLM 在 System Prompt 中完成。

在 save_chats_to_long_term_memory 写入原始消息的同时调用本模块，
生成 type="context_analysis" 的结构化指标文档存入 pgvector，
供 Agent 的 search_chat_context 工具检索。
"""
import hashlib
from datetime import datetime
from typing import List, Optional, Tuple

from langchain_core.documents import Document

from src.schemas import ChatMessage


# ══════════════════════════════════════════════════════════════
# 工具函数（纯数据计算，不做语义判断）
# ══════════════════════════════════════════════════════════════

def _quick_hash(text: str, length: int = 8) -> str:
    return hashlib.md5(text.encode()).hexdigest()[:length]


def _parse_time(ts: str) -> Optional[datetime]:
    """尝试多种常见时间格式解析。"""
    formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y/%m/%d %H:%M:%S",
        "%Y/%m/%d %H:%M",
        "%m-%d %H:%M:%S",
        "%m-%d %H:%M",
        "%H:%M:%S",
        "%H:%M",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(ts.strip(), fmt)
        except (ValueError, AttributeError):
            continue
    return None


def _estimate_response_seconds(prev_ts: Optional[datetime], curr_ts: Optional[datetime]) -> Optional[float]:
    """估算两条消息间的响应间隔（秒）。超过 7 天视为新对话开始。"""
    if prev_ts is None or curr_ts is None:
        return None
    delta = (curr_ts - prev_ts).total_seconds()
    if delta < 0 or delta > 7 * 24 * 3600:
        return None
    return delta


def _fmt_seconds(seconds: float) -> str:
    """将秒数格式化为人类可读字符串。"""
    if seconds < 60:
        return f"{seconds:.0f}秒"
    elif seconds < 3600:
        return f"{seconds / 60:.1f}分钟"
    else:
        return f"{seconds / 3600:.1f}小时"


# ══════════════════════════════════════════════════════════════
# 核心 Pipeline：纯数据统计，零语义解读
# ══════════════════════════════════════════════════════════════

def engineer_chat_context(
    chats: List[ChatMessage],
    target_person: str,
) -> List[Document]:
    """
    将原始聊天记录预处理为**纯结构化指标文档**。

    Pipeline:
      1. 排序 + 去重
      2. 识别参与者
      3. 逐轮提取数值特征（字数、响应间隔、发起/终结标记）
      4. 聚合统计指标
      5. 打包为单个 Document → 存入 context_analysis collection

    输出是纯数据事实，不含任何"这意味着什么"的解读。
    解读工作由 LLM Agent 根据 System Prompt 中的标准自行完成。
    """
    if not chats:
        return []

    # ── 1. 排序 + 去重 ──
    parsed: List[Tuple[Optional[datetime], ChatMessage]] = []
    seen: set[str] = set()
    for c in chats:
        key = f"{c.sender}|{c.timestamp}|{c.content[:50]}"
        if key in seen:
            continue
        seen.add(key)
        parsed.append((_parse_time(c.timestamp), c))

    parsed.sort(key=lambda x: (x[0] is None, x[0] or datetime.min))
    sorted_chats = [p[1] for p in parsed]
    sorted_times = [p[0] for p in parsed]

    # ── 2. 识别参与者 ──
    participants = list(dict.fromkeys(c.sender for c in sorted_chats))
    other_party = target_person if target_person in participants else (
        participants[1] if len(participants) > 1 else participants[0]
    )
    me_candidates = [p for p in participants if p != other_party]
    me = me_candidates[0] if me_candidates else "我"

    # ── 3. 逐轮特征提取（仅数值，不做解读）──
    turn_records: List[str] = []
    me_lengths: List[int] = []
    other_lengths: List[int] = []
    me_to_other_gaps: List[float] = []    # 我 → 对方 响应间隔
    other_to_me_gaps: List[float] = []    # 对方 → 我 响应间隔
    me_initiate = 0
    other_initiate = 0
    me_end = 0
    other_end = 0

    CHAT_GAP_THRESHOLD = 3600  # 1小时以上视为新对话开始

    for i, chat in enumerate(sorted_chats):
        content_len = len(chat.content)
        is_me = chat.sender == me
        prev_time = sorted_times[i - 1] if i > 0 else None
        curr_time = sorted_times[i]
        gap = _estimate_response_seconds(prev_time, curr_time)

        # 是否为对话发起者
        is_initiator = (i == 0) or (gap is not None and gap > CHAT_GAP_THRESHOLD)
        if is_initiator:
            if is_me:
                me_initiate += 1
            else:
                other_initiate += 1

        # 是否为对话终结者
        is_ender = False
        if i == len(sorted_chats) - 1:
            is_ender = True
        else:
            next_time = sorted_times[i + 1]
            next_gap = _estimate_response_seconds(curr_time, next_time)
            if next_gap is not None and next_gap > CHAT_GAP_THRESHOLD:
                is_ender = True
        if is_ender:
            if is_me:
                me_end += 1
            else:
                other_end += 1

        # 消息长度
        if is_me:
            me_lengths.append(content_len)
        else:
            other_lengths.append(content_len)

        # 响应间隔
        if gap is not None:
            if is_me and i > 0 and sorted_chats[i - 1].sender == other_party:
                other_to_me_gaps.append(gap)
            elif not is_me and i > 0 and sorted_chats[i - 1].sender == me:
                me_to_other_gaps.append(gap)

        # 时序记录
        flags = []
        if is_initiator:
            flags.append("发起")
        if is_ender:
            flags.append("终结")
        flag_str = f" | {', '.join(flags)}" if flags else ""
        turn_records.append(
            f"[{chat.timestamp}] {chat.sender} | {content_len}字{flag_str}"
        )

    total = len(sorted_chats)
    me_count = sum(1 for c in sorted_chats if c.sender == me)
    other_count = total - me_count

    def _avg(lst: List) -> str:
        return f"{sum(lst) / len(lst):.0f}" if lst else "N/A"

    def _avg_gap(lst: List[float]) -> str:
        return _fmt_seconds(sum(lst) / len(lst)) if lst else "N/A"

    ratio = f"{me_count / other_count:.2f}" if other_count > 0 else "N/A"

    conv_id = _quick_hash(f"{target_person}:{sorted_chats[0].timestamp}:{sorted_chats[-1].timestamp}")

    # ── 4. 构建纯结构化指标文档（无任何"⚠️/✅"等语义标签）──
    metrics_text = f"""# 对话统计指标
- 对话ID: {conv_id}
- 参与者: {', '.join(participants)}
- 分析目标: {target_person}
- 时间跨度: {sorted_chats[0].timestamp} → {sorted_chats[-1].timestamp}

## 消息量
- 总计: {total} 条
- 我 ({me}): {me_count} 条
- {other_party}: {other_count} 条
- 比例 (我 : {other_party}) = 1 : {ratio}

## 主动性
- 我发起对话: {me_initiate} 次
- {other_party}发起对话: {other_initiate} 次
- 发起比 (我 : {other_party}) = {me_initiate} : {other_initiate}
- 我终结对话: {me_end} 次
- {other_party}终结对话: {other_end} 次

## 消息长度
- 我平均消息长度: {_avg(me_lengths)} 字
- {other_party}平均消息长度: {_avg(other_lengths)} 字

## 响应时间
- 我 → {other_party} 平均响应间隔: {_avg_gap(me_to_other_gaps)}
- {other_party} → 我 平均响应间隔: {_avg_gap(other_to_me_gaps)}

## 逐轮时序
{chr(10).join(turn_records)}
"""

    # ── 5. 打包为 Document ──
    return [
        Document(
            page_content=metrics_text,
            metadata={
                "type": "context_analysis",
                "subtype": "conversation_metrics",
                "target_person": target_person,
                "conversation_id": conv_id,
            },
        ),
    ]


# ══════════════════════════════════════════════════════════════
# 工具函数：构建单条消息的原文索引（供 deep_read_message 使用）
# ══════════════════════════════════════════════════════════════

def build_message_index_docs(
    chats: List[ChatMessage],
    target_person: str,
) -> List[Document]:
    """
    为每条消息生成独立的索引文档，metadata 中包含 message_id，
    供 deep_read_message 工具按 ID 精确定位原文。
    """
    docs = []
    for i, chat in enumerate(chats):
        msg_id = _quick_hash(f"{chat.sender}:{chat.timestamp}:{chat.content}", 12)
        docs.append(Document(
            page_content=f"[{chat.timestamp}] {chat.sender}: {chat.content}",
            metadata={
                "type": "message_index",
                "target_person": target_person,
                "message_id": msg_id,
                "sender": chat.sender,
                "timestamp": chat.timestamp,
                "seq": i,
            },
        ))
    return docs
