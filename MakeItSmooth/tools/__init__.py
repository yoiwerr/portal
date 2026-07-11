"""
MakeItSmooth 工具注册表 — 10 个工具。

信息检索 (4):
  - search_knowledge_base   PGVector 向量检索  [P0 优先]
  - search_web              Tavily 联网搜索    [P1 本地不够用]
  - fetch_url               抓取网页内容        [P2 深入阅读]
  - search_chat_history     对话历史检索        [P3 按需]

代码执行 (1):
  - python_exec             沙箱 Python        [按需，需 SANDBOX_ENABLED]

知识管理 (2):
  - add_to_knowledge_base   对话知识写入向量库   [按需]
  - list_knowledge_sources  知识库状态查询      [按需]

系统感知 (1):
  - run_shell_preview       只读 Shell          [按需]

Multi-Agent (1):
  - delegate_task           委托子 Agent        [P4 兜底，成本高]

文本处理 (3):
  - parse_text              结构化提取          [按需，规则引擎]
  - compare_texts           文本对比            [按需，规则引擎]
  - summarize_text          文本摘要            [按需，规则引擎，非 LLM]

调用优先级链:
  search_kb(P0) → search_web(P1) → fetch_url(P2) → delegate_task(P4 兜底)

用法:
    from tools import ALL_TOOLS, get_tools_for_skill
    agent = create_react_agent(model, tools=ALL_TOOLS)
"""

from tools.search import search_knowledge_base, search_web, fetch_url, search_chat_history
from tools.code import python_exec
from tools.knowledge import add_to_knowledge_base, list_knowledge_sources
from tools.shell import run_shell_preview
from tools.delegate import delegate_task
from tools.text import parse_text, compare_texts, summarize_text

ALL_TOOLS = [
    # P0 — 信息检索（优先使用）
    search_knowledge_base,
    search_web,
    fetch_url,
    search_chat_history,
    # 代码执行
    python_exec,
    # 知识管理
    add_to_knowledge_base,
    list_knowledge_sources,
    # 系统感知
    run_shell_preview,
    # Multi-Agent
    delegate_task,
    # 文本处理（规则引擎）
    parse_text,
    compare_texts,
    summarize_text,
]

# 按 Skill 推荐的子集（避免给模型太多选择）
SKILL_TOOL_MAP = {
    "prompt_refiner": [
        search_knowledge_base, search_web, fetch_url,
        add_to_knowledge_base, parse_text, compare_texts,
        delegate_task,
    ],
    "work_arranger":  [
        search_knowledge_base, search_web, fetch_url,
        add_to_knowledge_base, run_shell_preview,
        parse_text, delegate_task,
    ],
    "info_retention": [
        add_to_knowledge_base, list_knowledge_sources,
        summarize_text, parse_text,
    ],
    "research":       [
        search_web, fetch_url, search_knowledge_base,
        add_to_knowledge_base, summarize_text, parse_text,
        delegate_task,
    ],
    "code_review":    [
        run_shell_preview, search_knowledge_base, search_web,
        compare_texts, parse_text,
    ],
    "data_analysis":  [
        python_exec, search_knowledge_base,
        parse_text, summarize_text,
    ],
}


def get_tools_for_skill(skill_name: str):
    return SKILL_TOOL_MAP.get(skill_name, ALL_TOOLS)
