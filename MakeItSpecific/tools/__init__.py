"""
Alfred 工具注册表 — 7 个工具（4 个 Skill 共享 + 3 个预留）。

每个工具有明确的责任边界，无功能重叠：

  Skill 共享 (所有 Skill 可用):
    search_knowledge_base    — 读：PGVector 向量检索领域知识    [P0 必须]
    add_to_knowledge_base    — 写：对话知识持久化到向量库       [用户触发]
    save_project_memory      — 基于三层记忆生成项目记忆 .md    [用户触发]
    export_markdown          — 导出文档为 .md 供下载            [用户触发]

  预留 (未分配给 Skill，仅 ALL_TOOLS 持有):
    python_exec              — 沙箱 Python：精确计算/格式转换    [预留]
    run_shell_preview        — 只读 Shell：查看项目结构/文件     [预留]
    write_file               — 受限文件写入：data/exports/ 目录  [预留]

阿福身份定位是"协作引导者"而非"执行者"，因此 Skill 不暴露预留工具。

用法:
    from tools import ALL_TOOLS, get_tools_for_skill
    agent = create_react_agent(model, tools=get_tools_for_skill("prompt_refiner"))
"""

from tools.search import search_knowledge_base
from tools.code import python_exec
from tools.knowledge import add_to_knowledge_base
from tools.shell import run_shell_preview
from tools.fs import write_file
from tools.memory import save_project_memory, export_markdown

# ── 全局工具列表（7 个）──
ALL_TOOLS = [
    search_knowledge_base,
    python_exec,
    add_to_knowledge_base,
    run_shell_preview,
    write_file,
    save_project_memory,
    export_markdown,
]

# ── 按 Skill 推荐的工具子集 ──
# 每个 Skill 只暴露真正需要的工具，减少模型选择负担。
SKILL_TOOL_MAP = {
    "prompt_refiner": [
        search_knowledge_base,
        add_to_knowledge_base,
        save_project_memory,
        export_markdown,
    ],
    "work_arranger": [
        search_knowledge_base,
        add_to_knowledge_base,
        save_project_memory,
        export_markdown,
    ],
    "info_retention": [
        add_to_knowledge_base,
        search_knowledge_base,
        save_project_memory,
        export_markdown,
    ],
    "code_review": [
        search_knowledge_base,
        add_to_knowledge_base,
        save_project_memory,
        export_markdown,
    ],
}


def inject_services(rag_service=None, config=None, agent=None):
    """
    统一服务注入 — 由 Agent.__init__ 调用一次即可。
    将 RAG 服务和配置注入到所有需要它们的工具模块。
    """
    import tools.search as search_mod
    import tools.knowledge as knowledge_mod
    import tools.code as code_mod

    search_mod._rag_service = rag_service
    knowledge_mod._rag_service = rag_service
    code_mod._config = config

    from tools.fs import set_fs_tool_config
    set_fs_tool_config(config=config)

    from tools.memory import set_memory_tool_services
    set_memory_tool_services(agent=agent, config=config)


def get_tools_for_skill(skill_name: str):
    """返回指定 Skill 的工具子集。未注册的 Skill 返回全部工具。"""
    return SKILL_TOOL_MAP.get(skill_name, ALL_TOOLS)
