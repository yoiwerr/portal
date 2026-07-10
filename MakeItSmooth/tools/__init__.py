"""
MakeItSmooth 工具注册表 — 7 个工具（含 1 个 Meta Tool）。

信息检索:
  - search_knowledge_base   PGVector 向量检索
  - search_web              Tavily 联网搜索
  - fetch_url               抓取网页内容

代码执行:
  - python_exec             沙箱 Python

知识管理:
  - add_to_knowledge_base   对话知识写入向量库

系统感知:
  - run_shell_preview       只读 Shell（ls/cat/git status 等）

Multi-Agent:
  - delegate_task           委托子 Agent 独立执行子任务
                            子 Agent 只有搜索工具，不能再 spawn 子 Agent

用法:
    from tools import ALL_TOOLS
    agent = create_react_agent(model, tools=ALL_TOOLS)
"""

from tools.search import search_knowledge_base, search_web, fetch_url
from tools.code import python_exec
from tools.knowledge import add_to_knowledge_base
from tools.shell import run_shell_preview
from tools.delegate import delegate_task

ALL_TOOLS = [
    search_knowledge_base,
    search_web,
    fetch_url,
    python_exec,
    add_to_knowledge_base,
    run_shell_preview,
    delegate_task,
]

# 按 Skill 推荐的子集
SKILL_TOOL_MAP = {
    "prompt_refiner": [search_knowledge_base, search_web, add_to_knowledge_base, delegate_task],
    "work_arranger":  [search_knowledge_base, search_web, add_to_knowledge_base,
                       run_shell_preview, delegate_task],
    "info_retention": [add_to_knowledge_base, run_shell_preview],
    "research":       [search_web, fetch_url, search_knowledge_base, add_to_knowledge_base,
                       delegate_task],
    "code_review":    [run_shell_preview, search_knowledge_base, search_web],
    "data_analysis":  [python_exec, search_knowledge_base],
}


def get_tools_for_skill(skill_name: str):
    return SKILL_TOOL_MAP.get(skill_name, ALL_TOOLS)
