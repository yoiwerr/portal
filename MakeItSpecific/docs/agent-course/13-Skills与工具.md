# 课程 13：Skills 与工具系统

> **难度**: 中级 | **预计阅读**: 20 分钟 | **前置**: [09-执行节点](09-执行节点.md)

---

## 一、架构概览

```
┌──────────────────────────────────────────────┐
│  Skills (4 个)                                │
│  ├─ PromptRefiner   提示词精炼师              │
│  ├─ WorkArranger    工作安排规划师            │
│  ├─ InfoRetention   信息留存                  │
│  └─ CodeReview      代码审查                  │
│                                              │
│  Tools (7 个)                                 │
│  ├─ search_knowledge_base   PGVector 检索     │
│  ├─ add_to_knowledge_base   写入知识库        │
│  ├─ save_project_memory     项目记忆摘要      │
│  ├─ export_markdown         Markdown 导出     │
│  ├─ python_exec             Python 沙箱(预留)  │
│  ├─ run_shell_preview       Shell 预览(预留)   │
│  └─ write_file              文件写入(预留)     │
│                                              │
│  工具注册表: SKILL_TOOL_MAP                   │
│    每个 Skill 只能看到它的工具子集              │
└──────────────────────────────────────────────┘
```

---

## 二、BaseSkill 抽象基类

```python
# skills/base.py

@dataclass
class SkillContext:
    """Skill 执行所需的完整上下文。"""
    original_message: str = ""
    expressed_dimensions: dict = field(default_factory=dict)
    background: str = ""
    rag_context: str = ""
    extra_context: str = ""
    completeness: float = 0.0


class BaseSkill(ABC):
    name: str = ""            # 唯一标识符
    label: str = ""           # 中文名称
    description: str = ""     # 一句话描述
    icon: str = "✨"          # 图标 emoji

    @abstractmethod
    async def execute(self, context: SkillContext, model) -> str:
        """执行 Skill 逻辑。返回 Markdown 格式的完整输出。"""
        ...

    def get_input_placeholder(self) -> str:
        """获取输入框的占位文本。"""
        return "请描述你的需求..."
```

---

## 三、如何添加新 Skill

```python
# skills/my_skill.py
from skills.base import BaseSkill, SkillContext

class MySkill(BaseSkill):
    name = "my_skill"
    label = "我的技能"
    icon = "🔧"
    description = "一句话描述"

    async def execute(self, context: SkillContext, model) -> str:
        # 实现技能逻辑
        return "输出内容"
```

然后在 `core/agent.py` 中注册：

```python
from skills.my_skill import MySkill
self.skills["my_skill"] = MySkill()
```

还需要：

1. 在 `prompts/system_prompts.py` 中添加对应的 Skill System Prompt
2. 在 `prompts/templates.py` 的 `MODULE_DIMENSIONS` 中添加维度定义
3. 在 `core/router.py` 的 `SCENE_TO_MODULE` 中添加路由映射（如需自动识别）
4. 在 `tools/__init__.py` 的 `SKILL_TOOL_MAP` 中配置工具子集

---

## 四、工具注册表

### 4.1 全局工具列表

```python
# tools/__init__.py
ALL_TOOLS = [
    search_knowledge_base,    # P0: 知识库检索
    python_exec,              # 预留: Python 沙箱
    add_to_knowledge_base,    # 知识持久化
    run_shell_preview,        # 预留: Shell 预览
    write_file,               # 预留: 文件写入
    save_project_memory,      # 项目记忆摘要
    export_markdown,          # Markdown 导出
]
```

### 4.2 Skill → Tool 映射

```python
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
    # info_retention, code_review 同理
}

def get_tools_for_skill(skill_name: str):
    return SKILL_TOOL_MAP.get(skill_name, ALL_TOOLS)
```

> **当前设计**: 所有 4 个 Skill 共享相同的工具子集（4 个核心工具），3 个预留工具未分配。

---

## 五、工具服务注入

```python
def inject_services(rag_service=None, config=None, agent=None):
    """统一服务注入 — Agent.__init__ 调用一次即可。"""

    # search_knowledge_base 和 add_to_knowledge_base 需要 RAG
    import tools.search as search_mod
    import tools.knowledge as knowledge_mod
    search_mod._rag_service = rag_service
    knowledge_mod._rag_service = rag_service

    # python_exec 需要 config
    import tools.code as code_mod
    code_mod._config = config

    # fs tools 需要 config
    from tools.fs import set_fs_tool_config
    set_fs_tool_config(config=config)

    # memory tools 需要 agent + config
    from tools.memory import set_memory_tool_services
    set_memory_tool_services(agent=agent, config=config)
```

---

## 六、工具 docstring 规范

每个 `@tool` 函数使用标准化的三段式 docstring：

```python
@tool
async def search_knowledge_base(query: str) -> str:
    """
    【用途】从本地知识库 (PGVector) 向量检索领域知识。

    【什么时候用】
    - Executor 需要精确引用知识库内容时
    - 被动注入的 RAG 上下文不够具体
    - 用户要求 "查一下知识库里怎么说"

    【坚决不用】
    - 常识性问题 — 模型自身知识已足够
    - 纯创意/头脑风暴 — 不需要检索事实
    - 用户明确说 "不要查资料"

    【与其他 tool 的关系】
    - 与 add_to_knowledge_base: 读写分离。search_kb 只读不写。

    【参数】query: 搜索查询。用关键词而非完整句子。中英混合最佳。
    【返回】JSON 字符串: {"hit": bool, "results": [...], "total_scanned": int}
    """
```

> **为什么这么详细？** LLM 通过 docstring 理解工具的用途、边界和参数。详细的 docstring 显著减少误调用。

---

## 七、两个特殊工具

### 7.1 export_markdown — 文档导出

```
工作流:
  1. 阿福用模型知识写好 Markdown 内容
  2. 调用 export_markdown(title="文档标题", content="完整内容")
  3. 用户点击返回的下载链接
```

### 7.2 save_project_memory — 项目记忆

```
工作流:
  1. 工具从 context_engine + sessions + contract_store 收集三层记忆
  2. LLM 合成为结构化 JSON (8 个板块)
  3. 渲染为固定格式 Markdown
  4. 写入 data/exports/ 返回下载链接
```

与 export_markdown 的区别：
| | export_markdown | save_project_memory |
|--|----------------|---------------------|
| 内容来源 | 阿福手写 | 对话上下文自动合成 |
| 耗时 | 秒级 | ~5-10s (LLM 合成) |
| 用途 | 交付文档 | 存档会话 |

---

## 八、阿福身份定义

所有 System Prompt 共享同一份身份定义 (`_ALFRED_IDENTITY`)：

```python
_ALFRED_IDENTITY = """## 🔔 你的身份：阿福（Alfred）— AI 协作管家

你位于用户与执行型 Agent 之间，是 AI 协作中间层管家。

### 你擅长的
1. 帮用户把模糊想法追问成清晰目标
2. 发现用户漏掉的关键信息
3. 把需求整理成结构化的任务契约
4. 根据知识库推荐合适的工具和方法

### 你不做的
| 用户的请求 | 你不做 | 你推荐 |
|-----------|--------|--------|
| 写代码     | 不写一行代码 | Claude / Cursor / Copilot |
| 深度研究   | 不联网搜索   | ChatGPT / Perplexity |
| 执行命令   | 不执行命令   | 告诉用户怎么做 |

### 工具调用铁律（违反即错误）
调用任何工具之前，必须确认以下六条全部成立：
1. 工具能明显提高准确性、降低风险
2. 当前上下文不足以可靠完成
3. 工具用途与当前目标直接相关
4. 不会越过用户授权和边界
5. 工具结果可以被验证
6. 本轮没有无意义地重复同一操作
"""
```

---

## 九、关键要点

1. **BaseSkill 是最小接口** — 只需实现 `execute(context, model) -> str`
2. **工具子集减少选择负担** — 每个 Skill 只看到 4 个工具而非 7 个
3. **服务注入是一次性的** — `inject_services()` 设置模块级变量
4. **详细的 docstring = 更少的误调用** — LLM 通过 docstring 理解工具
5. **阿福身份共享** — 所有 Skill System Prompt 都包含同一个 `_ALFRED_IDENTITY`

---

## 十、继续学习

→ [14-任务契约](14-任务契约.md) — TaskContract Pydantic 模型详解
