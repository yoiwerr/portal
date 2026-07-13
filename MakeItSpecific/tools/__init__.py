"""
MakeItSpecific 工具注册表 — 4 个工具。

每个工具有明确的责任边界，无功能重叠：

  知识库 (2):
    search_knowledge_base    — 读：PGVector 向量检索领域知识    [P0 必须]
    add_to_knowledge_base    — 写：对话知识持久化到向量库       [用户触发]

  代码执行 (1):
    python_exec              — 沙箱 Python：精确计算/格式转换    [按需]

  系统感知 (1):
    run_shell_preview        — 只读 Shell：查看项目结构/文件     [按需]

  文件写入 (1):
    write_file               — 受限文件写入：data/exports/ 目录   [按需]

调用优先级链:
  search_knowledge_base (P0 — 涉及技术选型/工具推荐/方法论时必调)
    → python_exec (需要精确计算/格式转换时)
      → run_shell_preview (需要看文件系统时)
        → add_to_knowledge_base (用户要求保存时)

与旧版的差异:
  删除 search_web         — 不再用 Apikey 联网搜，RAG + 模型自身能力覆盖
  删除 fetch_url          — 同上，不发起外网 HTTP 请求
  删除 search_chat_history — ContextEngine (L1+L2+L3) 自动注入历史，无需手动检索
  删除 delegate_task      — 子 Agent 只有 search_kb 无额外价值，executor 自身已覆盖
  删除 parse_text         — 规则引擎，LLM 原生结构化提取更好
  删除 compare_texts      — 规则引擎行级 diff，LLM 语义对比更好
  删除 summarize_text     — 规则引擎截断器，LLM 原生摘要更好
  删除 list_knowledge_sources — KB 统计是系统运维操作，不是对话工具

用法:
    from tools import ALL_TOOLS, get_tools_for_skill
    agent = create_react_agent(model, tools=get_tools_for_skill("prompt_refiner"))
"""

from tools.search import search_knowledge_base
from tools.code import python_exec
from tools.knowledge import add_to_knowledge_base
from tools.shell import run_shell_preview
from tools.fs import write_file

# ── 全局工具列表（5 个）──
ALL_TOOLS = [
    search_knowledge_base,
    python_exec,
    add_to_knowledge_base,
    run_shell_preview,
    write_file,
]

# ── 按 Skill 推荐的工具子集 ──
# 每个 Skill 只暴露真正需要的工具，减少模型选择负担。
SKILL_TOOL_MAP = {
    "prompt_refiner": [
        search_knowledge_base,
        add_to_knowledge_base,
    ],
    "work_arranger": [
        search_knowledge_base,
        add_to_knowledge_base,
        run_shell_preview,
        write_file,
    ],
    "info_retention": [
        add_to_knowledge_base,
        search_knowledge_base,
        write_file,
    ],
    "code_review": [
        run_shell_preview,
        search_knowledge_base,
        add_to_knowledge_base,
    ],
}


def inject_services(rag_service=None, config=None):
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


def get_tools_for_skill(skill_name: str):
    """返回指定 Skill 的工具子集。未注册的 Skill 返回全部工具。"""
    return SKILL_TOOL_MAP.get(skill_name, ALL_TOOLS)
