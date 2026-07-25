"""
Alfred Agent Tool — 项目记忆导出。

save_project_memory : 基于三层记忆 (L1/L2/L3) + 任务契约，生成结构化项目记忆 .md 文件。
                      用户明确要求「保存对话」「导出记忆」「存下来下次继续」时调用。
                      写入 data/exports/ 目录，返回路径供下载。
"""

import json
import logging
from pathlib import Path
from datetime import datetime, timezone

from langchain_core.tools import tool

logger = logging.getLogger(__name__)

# ── 注入的服务（由 Agent.__init__ → tools.inject_services 填充）──
_agent = None          # Agent 实例引用
_export_dir = None     # 导出目录

# ── 固定模板（文档骨架，由 LLM 按实际内容填充，空节跳过）──
MEMORY_TEMPLATE = """---
document_type: project_memory
schema_version: "1.0"
project_name: "{project_name}"
title: "{title}"
source_session_id: "{session_id}"
created_at: "{created_at}"
updated_at: "{updated_at}"
language: "zh-CN"
focus: "{focus}"
status: "in_progress"
---

# 项目记忆摘要

{body}"""


def set_memory_tool_services(agent=None, config=None):
    """注入 Agent 实例和配置。"""
    global _agent, _export_dir
    _agent = agent
    if config:
        raw = getattr(config, "export_dir", None) or (
            Path(getattr(config, "project_root", ".")) / "data" / "exports"
        )
        _export_dir = Path(raw).resolve()
    else:
        _export_dir = Path("data/exports").resolve()


# ============================================================
# LLM 合成 Prompt
# ============================================================

SYNTHESIS_PROMPT = """你是项目记忆整理助手。根据提供的对话上下文与任务契约，生成一份结构化的项目记忆文档。

## 输出格式（严格 JSON）

{{
  "project_name": "项目名称",
  "title": "本次记忆摘要标题（15 字以内）",
  "focus": "本次主要讨论主题（一句话）",
  "sections": {{
    "quick_restore": "快速恢复：用一至两个自然段概括当前项目是什么、用户想完成什么、当前进度、下一步。",
    "goals": {{
      "final_goal": "最终目标",
      "stage_goal": "当前阶段目标",
      "deliverables": "预期交付物",
      "scenarios": "主要使用场景"
    }},
    "contract": {{
      "goal": "当前目标（来自任务契约）",
      "scope_in": ["包含项"],
      "scope_out": ["暂不包含项"],
      "known_conditions": ["已知条件"],
      "constraints": ["约束与偏好"],
      "acceptance": ["验收标准"],
      "risks": ["风险边界"]
    }},
    "decisions": [
      {{"name": "决策名称", "conclusion": "结论", "status": "已确认", "reason": "原因", "scope": "影响范围", "source": "用户明确选择"}}
    ],
    "abandoned": [
      {{"name": "原方案名称", "status": "已否决/已被替代", "original": "原方案", "current": "当前方案", "reason": "原因", "note": "后续不要自动恢复该方案"}}
    ],
    "progress": {{
      "completed": ["已完成事项"],
      "generated_not_done": [{{"artifact": "产物", "usage": "用途", "status": "待执行/待验证/待确认"}}],
      "in_progress": ["正在进行"],
      "not_started": ["尚未开始"]
    }},
    "artifacts": [
      {{"name": "产物名称", "type": "类型", "usage": "用途", "status": "状态", "files": "相关文件", "content_brief": "关键内容（不要复制过长完整产物）", "notes": "注意事项"}}
    ],
    "tech_info": {{
      "stack": "技术栈",
      "framework": "主要框架",
      "storage": "数据存储",
      "external": "外部模型或服务",
      "runtime": "运行方式",
      "modules": [{{"name": "模块名称", "role": "作用", "status": "当前状态", "interfaces": "相关接口或文件"}}],
      "data_structures": [{{"name": "函数或工具名称", "schema": "Schema", "fields": "重要字段", "input": "输入", "output": "输出", "limits": "异常或限制"}}],
      "key_flows": "关键流程"
    }}
  }}
}}

## 规则
- 只写已有信息，严禁编造
- 空字段返回 "" 或 []，不要写「暂无」「待补充」
- decisions 只写用户明确确认的选择，不写 AI 建议
- abandoned 写被否决或被替代的方案及其原因
- 每个 section 没有相关内容就不写，不要为了凑数编造
- 用第三人称描述用户偏好和决策

## 可供编写的信息来源

### 任务契约
{contract_text}

### 最近对话 (L1)
{l1_text}

### 历史摘要 (L2)
{l2_text}

### 语义事实 (L3)
{l3_text}

只输出 JSON，不要其他内容。"""


# ============================================================
# Markdown 渲染
# ============================================================

def _render_markdown(data: dict) -> str:
    """将 LLM 输出的 JSON 渲染为固定格式 Markdown。每个板块没有相关内容就不写。"""
    sections = data.get("sections", {})
    lines = []

    # ── 一、快速恢复 ──
    qr = sections.get("quick_restore", "").strip()
    if qr:
        lines.append("## 一、快速恢复\n")
        lines.append(qr + "\n")

    # ── 二、项目目标 ──
    goals = sections.get("goals", {})
    if goals:
        has_goal = any(goals.get(k) for k in ["final_goal", "stage_goal", "deliverables", "scenarios"])
        if has_goal:
            lines.append("## 二、项目目标\n")
            if goals.get("final_goal"):
                lines.append(f"- **最终目标：** {goals['final_goal']}")
            if goals.get("stage_goal"):
                lines.append(f"- **当前阶段目标：** {goals['stage_goal']}")
            if goals.get("deliverables"):
                lines.append(f"- **预期交付物：** {goals['deliverables']}")
            if goals.get("scenarios"):
                lines.append(f"- **主要使用场景：** {goals['scenarios']}")
            lines.append("")

    # ── 三、任务契约 ──
    contract = sections.get("contract", {})
    if contract:
        has_contract = any(contract.get(k) and (isinstance(contract[k], list) and len(contract[k]) > 0 or isinstance(contract[k], str) and contract[k].strip())
                          for k in contract if k != "scope_in" and k != "scope_out")
        scope_in = contract.get("scope_in", [])
        scope_out = contract.get("scope_out", [])
        if has_contract or scope_in or scope_out:
            lines.append("## 三、任务契约\n")
            if contract.get("goal"):
                lines.append("### 3.1 当前目标\n")
                lines.append(f"- {contract['goal']}\n")
            if scope_in or scope_out:
                lines.append("### 3.2 工作范围\n")
                if scope_in:
                    lines.append("#### 包含\n")
                    for item in scope_in:
                        lines.append(f"- {item}")
                    lines.append("")
                if scope_out:
                    lines.append("#### 暂不包含\n")
                    for item in scope_out:
                        lines.append(f"- {item}")
                    lines.append("")
            for key, label in [("known_conditions", "3.3 已知条件"), ("constraints", "3.4 约束与偏好"),
                               ("acceptance", "3.5 验收标准"), ("risks", "3.6 风险边界")]:
                items = contract.get(key, [])
                if items:
                    lines.append(f"### {label}\n")
                    for item in items:
                        lines.append(f"- {item}")
                    lines.append("")

    # ── 四、已确认决策 ──
    decisions = sections.get("decisions", [])
    if decisions:
        lines.append("## 四、已确认决策\n")
        for i, d in enumerate(decisions, 1):
            name = d.get("name", f"决策 {i:02d}")
            lines.append(f"### 决策 {i:02d}：{name}\n")
            for k, label in [("conclusion", "结论"), ("status", "状态"), ("reason", "原因"),
                             ("scope", "影响范围"), ("source", "确认来源")]:
                if d.get(k):
                    lines.append(f"- **{label}：** {d[k]}")
            lines.append("")
    else:
        lines.append("## 四、已确认决策\n")
        lines.append("暂无。\n")

    # ── 五、已放弃或被替代的方案 ──
    abandoned = sections.get("abandoned", [])
    if abandoned:
        lines.append("## 五、已放弃或被替代的方案\n")
        for i, a in enumerate(abandoned, 1):
            name = a.get("name", f"方案 {i:02d}")
            lines.append(f"### 方案 {i:02d}：{name}\n")
            for k, label in [("status", "状态"), ("original", "原方案"), ("current", "当前方案"),
                             ("reason", "原因"), ("note", "注意")]:
                if a.get(k):
                    lines.append(f"- **{label}：** {a[k]}")
            lines.append("")

    # ── 六、当前进度 ──
    progress = sections.get("progress", {})
    if progress:
        has_prog = any(progress.get(k) for k in progress)
        if has_prog:
            lines.append("## 六、当前进度\n")
            completed = progress.get("completed", [])
            if completed:
                lines.append("### 6.1 已完成\n")
                for item in completed:
                    lines.append(f"- {item}")
                lines.append("")
            generated = progress.get("generated_not_done", [])
            if generated:
                lines.append("### 6.2 已生成但尚未实施\n")
                for g in generated:
                    if isinstance(g, dict):
                        lines.append(f"- **产物：** {g.get('artifact', '')}")
                        if g.get("usage"):
                            lines.append(f"- **用途：** {g['usage']}")
                        if g.get("status"):
                            lines.append(f"- **状态：** {g['status']}")
                    else:
                        lines.append(f"- {g}")
                lines.append("")
            in_prog = progress.get("in_progress", [])
            if in_prog:
                lines.append("### 6.3 正在进行\n")
                for item in in_prog:
                    lines.append(f"- {item}")
                lines.append("")
            not_started = progress.get("not_started", [])
            if not_started:
                lines.append("### 6.4 尚未开始\n")
                for item in not_started:
                    lines.append(f"- {item}")
                lines.append("")

    # ── 七、关键产物 ──
    artifacts = sections.get("artifacts", [])
    if artifacts:
        lines.append("## 七、关键产物\n")
        for i, a in enumerate(artifacts, 1):
            name = a.get("name", f"产物 {i:02d}")
            lines.append(f"### 产物 {i:02d}：{name}\n")
            for k, label in [("type", "类型"), ("usage", "用途"), ("status", "当前状态"),
                             ("files", "相关文件"), ("content_brief", "关键内容"), ("notes", "注意事项")]:
                if a.get(k):
                    lines.append(f"- **{label}：** {a[k]}")
            lines.append("")

    # ── 八、关键实现信息 ──
    tech = sections.get("tech_info", {})
    if tech:
        has_tech = any(tech.get(k) for k in tech if k not in ("modules", "data_structures"))
        modules = tech.get("modules", [])
        ds_list = tech.get("data_structures", [])
        if has_tech or modules or ds_list:
            lines.append("## 八、关键实现信息\n")

            basics = []
            for k, label in [("stack", "技术栈"), ("framework", "主要框架"), ("storage", "数据存储"),
                             ("external", "外部模型或服务"), ("runtime", "运行方式")]:
                if tech.get(k):
                    basics.append(f"- **{label}：** {tech[k]}")
            if basics:
                lines.append("### 8.1 技术结构\n")
                lines.extend(basics)
                lines.append("")

            if modules:
                lines.append("### 8.2 重要模块\n")
                for m in modules:
                    lines.append(f"- **{m.get('name', '')}**")
                    if m.get("role"):
                        lines.append(f"  - 作用：{m['role']}")
                    if m.get("status"):
                        lines.append(f"  - 当前状态：{m['status']}")
                    if m.get("interfaces"):
                        lines.append(f"  - 相关接口或文件：{m['interfaces']}")
                    lines.append("")

            if ds_list:
                lines.append("### 8.3 数据结构与接口\n")
                for ds in ds_list:
                    lines.append(f"- **{ds.get('name', '')}**")
                    for k, label in [("schema", "Schema"), ("fields", "重要字段"), ("input", "输入"),
                                     ("output", "输出"), ("limits", "异常或限制")]:
                        if ds.get(k):
                            lines.append(f"  - {label}：{ds[k]}")
                    lines.append("")

            flows = tech.get("key_flows", "")
            if flows:
                lines.append("### 8.4 关键流程\n")
                lines.append(flows + "\n")

    return "\n".join(lines)


# ============================================================
# Tool 1: export_markdown — 导出 Markdown 文件供下载
# ============================================================

@tool
async def export_markdown(
    title: str = "",
    content: str = "",
) -> str:
    """
    【用途】将你（阿福）生成的 Markdown 内容保存为 .md 文件，返回下载链接。
           你自己写内容、你自己决定结构，写完调用这个工具让用户下载。

    【什么时候用 — 这是你的"产出交付"工具】
    - 用户要一份文档：README、计划书、会议纪要、技术方案、使用指南……任何能用 Markdown 写的文档
    - 用户说「导出」「下载」「生成一份 xxx 文档」「帮我写一份 xxx 然后给我下载」
    - 你已经用模型自身能力写出了 Markdown 格式的完整内容，需要给用户一个文件
    - 用户说「把上面的内容存成文件」

    【核心工作流】
    1. 用你的模型知识把内容写好（结构清晰、Markdown 格式）
    2. 调用 export_markdown(title="文档标题", content="你写好的完整内容")
    3. 用户点击返回的下载链接拿走 .md 文件

    【坚决不用】
    - 内容还没写完 — 先把完整的 Markdown 写完再调
    - 内容太短（< 50 字符）—— 不值得下载
    - 用户要的是「把整个对话整理成项目记忆摘要」—— 用 save_project_memory

    【参数】
    - title:   文档标题（用于文件名，如 "项目README""技术方案V1"）
    - content: 你写好的完整 Markdown 文本

    【返回】下载链接和文件信息。用户点击即可下载 .md 文件。

    【与 save_project_memory 的区别】
    - export_markdown: 你写内容、你调工具、用户下载。适合「产出一份文档」。秒级完成。
    - save_project_memory: 从对话上下文（L1/L2/L3 + 契约）自动合成结构化摘要。适合「把这次聊天的上下文整理成项目记忆」。需要 LLM 合成，~5-10s。
    """
    global _agent, _export_dir

    if not content or len(content.strip()) < 50:
        return "⚠️ 内容过短（< 50 字符），拒绝导出。请先写好完整的文档内容。"

    if _export_dir is None:
        _export_dir = Path("data/exports").resolve()

    safe_title = title.strip() or "文档"
    # 安全文件名：保留中英文/数字/下划线/连字符
    import re
    safe_title = re.sub(r'[^一-鿿\w\-]', '_', safe_title)
    safe_title = re.sub(r'_+', '_', safe_title).strip('_') or 'untitled'
    safe_title = safe_title[:40]

    now = datetime.now(timezone.utc)
    ts = now.strftime("%Y%m%d_%H%M%S")
    filename = f"{safe_title}_{ts}.md"

    try:
        _export_dir.mkdir(parents=True, exist_ok=True)
        filepath = _export_dir / filename
        filepath.write_text(content, encoding="utf-8")

        download_url = f"/api/files/download?path={filename}"
        logger.info(f"[export_markdown] 已保存: {filepath} ({len(content)} 字符)")

        return (
            f"✅ 文档已导出。\n\n"
            f"- **文件**: {filename}\n"
            f"- **大小**: {len(content)} 字符\n"
            f"- **下载**: [{filename}]({download_url})\n\n"
            f"提示：点击链接下载 .md 文件。"
        )
    except Exception as e:
        logger.error(f"[export_markdown] 写入失败: {e}")
        return f"⚠️ 文件写入失败: {e}"


# ============================================================
# Tool 2: save_project_memory — 对话上下文 → 结构化项目记忆摘要
# ============================================================

@tool
async def save_project_memory(
    project_name: str = "",
    title: str = "",
    focus: str = "",
) -> str:
    """
    【用途】将当前会话的完整上下文（最近对话 + 历史摘要 + 语义事实 + 任务契约），
           通过 LLM 合成为一份结构化的项目记忆 .md 文件，供下次导入恢复工作状态。

    【什么时候用 — 这是你的"会话存档"工具】
    - 用户明确说「保存当前对话」「导出项目记忆」「存下来下次继续」
    - 本次工作告一段落，用户希望下次新会话能通过「读入项目记忆」恢复
    - 用户说「把这个项目的工作整理成交接文档」

    【坚决不用】
    - 用户只是要下载某一份文档（README、计划书等）—— 用 export_markdown
    - 对话刚开始、内容太少（< 3 轮）
    - 随口说「记住这个」—— 用 add_to_knowledge_base

    【参数】
    - project_name: 项目名称（可选，LLM 会自动推断）
    - title: 记忆摘要标题（可选，LLM 会自动生成）
    - focus: 本次主要讨论主题（可选）

    【返回】生成的 .md 文件路径和下载链接。

    【与 export_markdown 的区别】
    - save_project_memory: 从对话上下文自动合成。适合「存档会话」。需要 LLM 合成，~5-10s。
    - export_markdown: 你写内容、直接存。适合「交付文档」。秒级完成。
    """
    global _agent, _export_dir

    if _agent is None:
        return "⚠️ Agent 未初始化，无法生成项目记忆。"

    if _export_dir is None:
        _export_dir = Path("data/exports").resolve()

    session_id = ""
    contract = {}
    l1_text = ""
    l2_text = ""
    l3_text = ""

    # ── 收集三层记忆 + 契约 ──
    try:
        # 尝试获取当前 session（从最近的消息推断）
        if _agent.sessions:
            recent = _agent.sessions.list_sessions(limit=1)
            if recent:
                session_id = recent[0].get("id", "")
                # L1: 最近对话原文
                msgs = _agent.sessions.get_conversation(session_id)
                if msgs:
                    lines = []
                    for m in msgs[-6:]:  # 最近 3 轮 (user+assistant 各 3)
                        role = "👤 用户" if m.get("role") == "user" else "🤖 AI"
                        content = m.get("content", "")
                        lines.append(f"### {role}\n{content[:800]}\n")
                    l1_text = "\n".join(lines)

        # 从 context_engine 获取 L2 滚动摘要（依赖 session_id）
        if _agent.context_engine and session_id:
            l2_text = _agent.context_engine._running_summaries.get(session_id, "") or ""

        # 契约
        if _agent.contract_store and session_id:
            row = _agent.contract_store.get_latest(session_id)
            if row:
                contract = row.get("contract", {})

        # L3 事实
        if _agent.session_memory:
            try:
                query = contract.get("goal", "") or l2_text[:200] or "项目摘要"
                l3_text = await _agent.session_memory.retrieve(query, top_k=5)
            except Exception:
                l3_text = ""

    except Exception as e:
        logger.warning(f"[save_project_memory] 上下文收集部分失败: {e}")

    if not l1_text and not l2_text and not contract:
        return "⚠️ 当前会话内容太少，无法生成项目记忆。请先进行一些对话。"

    # ── 构建 prompt ──
    contract_text = json.dumps(contract, ensure_ascii=False, indent=2) if contract else "（无）"
    prompt = SYNTHESIS_PROMPT.format(
        contract_text=contract_text[:2000],
        l1_text=l1_text[:3000],
        l2_text=l2_text[:1500],
        l3_text=l3_text[:1000],
    )

    # ── LLM 合成 ──
    try:
        from langchain_core.messages import SystemMessage, HumanMessage
        structured_model = _agent.model.bind(response_format={"type": "json_object"})
        response = await structured_model.ainvoke([
            SystemMessage(content=prompt),
            HumanMessage(content="请输出 JSON。"),
        ])
        data = _parse_json(response.content)
        if not data or not data.get("sections"):
            return "⚠️ LLM 生成项目记忆失败，请重试。"
    except Exception as e:
        logger.error(f"[save_project_memory] LLM 合成失败: {e}")
        return f"⚠️ 生成项目记忆时出错: {e}"

    # ── 渲染 Markdown ──
    project = project_name or data.get("project_name", "未命名项目")
    ttl = title or data.get("title", "项目记忆摘要")
    fc = focus or data.get("focus", "")
    body = _render_markdown(data)

    now = datetime.now(timezone.utc)
    now_str = now.isoformat()
    md_content = MEMORY_TEMPLATE.format(
        project_name=project,
        title=ttl,
        session_id=session_id,
        created_at=now_str,
        updated_at=now_str,
        focus=fc,
        body=body,
    )

    # ── 写入文件 ──
    try:
        _export_dir.mkdir(parents=True, exist_ok=True)
        safe_name = project.replace(" ", "_").replace("/", "_")[:30]
        ts = now.strftime("%Y%m%d_%H%M%S")
        filename = f"alfred_memory_{safe_name}_{ts}.md"
        filepath = _export_dir / filename
        filepath.write_text(md_content, encoding="utf-8")

        download_url = f"/api/files/download?path={filename}"
        logger.info(f"[save_project_memory] 已保存: {filepath} ({len(md_content)} 字符)")

        return (
            f"✅ 项目记忆摘要已生成。\n\n"
            f"- **文件**: {filename}\n"
            f"- **大小**: {len(md_content)} 字符\n"
            f"- **下载**: [{filename}]({download_url})\n\n"
            f"提示：下载后可在新会话中通过「读入项目记忆」导入，恢复工作状态。"
        )
    except Exception as e:
        logger.error(f"[save_project_memory] 写入失败: {e}")
        return f"⚠️ 文件写入失败: {e}"


def _parse_json(content: str) -> dict:
    """鲁棒 JSON 解析。"""
    import re
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass
    # 尝试提取 ```json ... ``` 块
    match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', content, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass
    # 尝试提取 { ... }
    match = re.search(r'\{.*\}', content, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    return {}
