MakeItSmooth 个人工作流增强 Agent 使用指南

最后更新：2026年7月2日


一、项目是什么

MakeItSmooth 是一个本地 AI 工作助手。你用大白话描述想做的事情，它会通过追问帮你把需求说清楚，然后输出优化后的提示词或者工作计划。

与直接跟大模型聊天的核心区别：它会追问你没说清楚的部分，而不是瞎猜。

技术栈：

    API 层：FastAPI + Uvicorn（REST API + SSE 流式）
    Agent 框架：LangGraph（状态图决策流）+ LangChain Agent（Skill 执行 + @tool）
    推理引擎：SGLang → ChatOpenAI 直连（OpenAI 兼容 API）
    存储：SQLite（对话记录）+ ChromaDB（知识库 RAG）
    模型：DeepSeek-R1-7B（通过 SGLang）
         后续换 Ollama / 自训练模型只需改 config.py 一行

目前需要启动 SGLang 服务后即可使用真模型。前端已完成（暗色主题三模块 UI + SSE 流式对话）。


二、怎么启动

第一步：安装依赖

    打开终端，进入项目目录
    执行：pip install -r requirements.txt

第二步：启动应用

    执行：python app.py
    打开浏览器访问：http://127.0.0.1:8000/docs 查看 API 文档
    健康检查：http://127.0.0.1:8000/api/health

首次启动会自动索引知识库，几秒钟就能完成。


三、三个功能介绍

进入页面后，首先会看到顶部的共用背景区域。建议在这里用大白话填写你的目的和想法，比如"我是一个前端开发者，正在做电商项目"。

然后选择下面的三个标签页：

功能一（提示词工程）

    用途：把你说的需求优化成高质量的 AI 提示词
    流程：
        在输入框用大白话写你想用 AI 做什么
        系统会追问你几个问题（比如目标受众是谁、偏好什么风格等）
        信息够了之后，输出 2-3 个不同策略的优化版提示词
        每个版本会标注适用模型和推荐理由

功能二（工作安排交流）

    用途：把想法变成可执行的工作计划
    流程：
        描述你想做的项目或任务
        系统追问目的、范围、时间、资源等问题
        输出完整的项目计划（含阶段划分、任务清单、时间线、工具推荐）

功能三（信息留存）

    用途：整理和保存信息，下次可以继续用
    流程：
        描述你想保存什么信息，或加载之前的 MD 文件
        系统把关键信息整理成结构化文档
        导出为 MD 文件，下次可通过加载按钮读回来


四、整体架构

整个系统分四层：

第一层：API 层（routers 文件夹）

    FastAPI REST API + SSE 流式接口
    routers/chat.py — POST /api/chat/stream（核心对话入口，SSE 流式）
    routers/sessions.py — GET/DELETE /api/sessions（会话管理）
    routers/knowledge.py — GET /api/knowledge/search（知识库查询）
    http://127.0.0.1:8000/docs — Swagger 自动生成

第二层：Agent 层（core/agent.py + core/graph.py）

    agent.py 是 API 层的统一入口
        封装了 LangGraph 图的调用
        管理会话持久化（SQLite）
        注入 Tool 服务实例给 Skills

    graph.py 是 LangGraph 状态图的定义
        图的执行流程：
          START → rag_retrieve → extract_assess → 条件分支
                                                        ├→ clarify → END
                                                        └→ execute → END
        每个节点是一个异步函数，接收和更新 AgentState
        条件路由：完整度低于 75% 且轮数小于 5 → 追问，否则 → 执行

    维度提取（Phase 1 用正则规则）：
        extract_assess 节点从用户消息中提取已表达的维度

    完整度计算：
        每个 Skill 定义了若干信息维度（必填和可选，各有权重）
        完整度 = 已表达维度权重之和 / 所有维度权重之和

    追问生成：
        clarify 节点根据信息缺口生成 1-3 个精准追问

    Skill 执行（LangChain Agent 模式）：
        execute 节点构建 SkillContext，调用对应 Skill 的 execute 方法
        Skill 内部用 create_agent(model, tools, system_prompt=...) 创建 Agent
        Agent 可以调用 search_knowledge_base / search_chat_history / search_web

第三层：功能模块（skills 文件夹）

    三个 Skill 都继承 base.py 里的 BaseSkill 基类
    每个 Skill 使用 LangChain Agent + Tools 模式执行
    prompt_refiner.py → Agent 输出 2-3 个优化提示词版本
    work_arranger.py → Agent 输出结构化工作计划
    info_retention.py → Agent 输出整理后的留存文档

第四层：数据服务（services + tools 文件夹）

    session_store.py：SQLite 存储对话记录（sessions 表 + messages 表）
    rag_service.py：ChromaDB 知识库检索（Phase 1 关键词匹配 → Phase 2 向量检索）
    md_export.py：Markdown 文件导入导出
    tools/search.py：LangChain @tool 定义 × 3


五、LLM 客户端设计

    core/llm_client.py 是 LLM 调用的统一抽象

    LLMClient 抽象接口：
        chat(prompt, system, temperature) → 非流式
        chat_stream(prompt, system, temperature) → 流式
        is_available() → 健康检查

    MockLLMClient（Phase 1 默认）：
        基于关键词匹配 + 模板填充

    SGLangClient（Phase 2）：
        通过 LangChain 的 ChatOpenAI 连接 SGLang
        SGLang 暴露 OpenAI 兼容 API（http://localhost:30000/v1）
        切换方式：设 USE_MOCK_LLM=false 环境变量

    LangChainLLMWrapper（新增）：
        把 LLMClient 包装成 LangChain 兼容的 BaseChatModel
        这样 create_agent() 可以直接使用 MockLLM/SGLang 作为模型


六、LangGraph 图详解

    图的定义在 core/graph.py，是整套系统最核心的文件。

    四个节点：

    节点1 rag_retrieve
        输入：用户消息
        处理：调用 RAG 服务从知识库检索相关知识
        输出：rag_context 字符串

    节点2 extract_assess
        输入：用户消息 + 历史维度 + 模块名
        处理：用正则规则提取维度 → 合并历史 → 计算完整度
        输出：expressed_dimensions + completeness

    节点3 clarify
        输入：信息缺口 + 完整度 + 追问轮数
        处理：根据缺口生成追问列表，格式化为用户友好的消息
        输出：output（追问消息），clarify_round 加一

    节点4 execute
        输入：完整的 expressed_dimensions + 背景 + RAG 上下文
        处理：调用对应模块的 execute 方法
        输出：output（模块生成的结果）

    条件路由 route_after_assess：
        completeness 小于 0.75 且 clarify_round 小于 5 → clarify
        否则 → execute


七、Agent 生命周期

    Agent（core/agent.py）是对 LangGraph 图的上层封装。

    每次用户发消息的处理流程：

        第一步：创建或获取 SQLite 会话
        第二步：保存用户消息到数据库
        第三步：构建 AgentState（把用户消息、模块、背景、历史维度等打包）
        第四步：运行 LangGraph 图（graph.ainvoke）
        第五步：判断结果类型
            如果 clarify_round 增加了 → 追问，保存追问消息，更新会话状态
            如果没增加 → 执行完成，保存结果，标记会话完成
        第六步：返回结构化结果给 UI 层


八、怎么从 Phase 1 切到 Phase 2

    Phase 1 当前状态：MockLLMClient + 关键词 RAG + 正则维度提取

    第一步：启动 SGLang 服务
        python -m sglang.launch_server --model deepseek-ai/DeepSeek-R1-Distill-Qwen-7B --port 30000

    第二步：设环境变量
        export USE_MOCK_LLM=false
        export SGLANG_BASE_URL=http://localhost:30000/v1

    第三步：重启应用
        python app.py

    改动范围：零代码修改，只改环境变量。

    第四步（可选）：升级 RAG 检索
        在 rag_service.py 中把 _DummyEmbeddingFunction 替换为 OllamaEmbeddingFunction
        或者用 SGLang 的 embedding 接口

    第五步（可选）：升级维度提取
        在 graph.py 的 extract_assess_node 中把规则提取改为 LLM 提取
        用 SGLangClient 调用 LLM，传入 extract prompt


九、目录结构速查

    app.py                       启动入口（FastAPI + 静态首页）
    config.py                    全局配置（SGLang URL、模型名、阈值）
    core/llm_client.py           create_model() → ChatOpenAI 工厂
    core/agent.py                Agent 封装层（API 的唯一入口）
    core/graph.py                LangGraph 状态图（4 节点 + 条件路由）
    skills/base.py               Skill 基类（BaseSkill + SkillContext）
    skills/prompt_refiner.py     Skill 1: 提示词工程（LangChain Agent）
    skills/work_arranger.py      Skill 2: 工作安排（LangChain Agent）
    skills/info_retention.py     Skill 3: 信息留存（LangChain Agent）
    tools/search.py              LangChain @tool × 3（知识库/历史/联网搜索）
    routers/chat.py              POST /api/chat/stream（SSE 流式）
    routers/sessions.py          会话管理（GET/DELETE）
    routers/knowledge.py         知识库查询
    models/schemas.py            Pydantic 请求/响应模型
    services/rag_service.py      ChromaDB 知识库检索
    services/session_store.py    SQLite 对话存储
    services/md_export.py        MD 文件导入导出
    static/index.html            首页（暗色主题 + 三模块卡片）
    static/css/style.css         首页样式
    static/js/chat.js            SSE 流式对话客户端
    static/js/particles.js       粒子背景动画
    prompts/system_prompts.py    各模块的系统提示词
    prompts/templates.py         追问模板 + 维度定义
    tests/                       单元测试（16 个）
    data/knowledge_base/         知识库 MD 文件


十、常见问题

    问：为什么启动时不需要启动 SGLang？
    答：Phase 1 使用 MockLLMClient，根据关键词返回模拟回复。全流程都能跑通但不依赖任何外部服务。

    问：SGLang 和 Ollama 的关系？
    答：SGLang 替代了 Ollama 作为推理引擎。SGLang 性能更高，支持更好的并发和批处理，暴露 OpenAI 兼容 API。通过 LangChain 的 ChatOpenAI 客户端连接。

    问：LangGraph 和 LangChain 的分工？
    答：LangGraph 负责状态管理和多步骤流程编排（追问还是执行的决策、节点间数据传递）。LangChain 提供 LLM 客户端抽象和 Prompt 模板工具。

    问：追问问得太少了怎么办？
    答：在 config.py 里把 clarify_threshold 调高（比如从 0.75 调到 0.85）。

    问：怎么往知识库里加东西？
    答：在 data/knowledge_base 文件夹里新建或粘贴 .md 文件，点界面上的重新索引按钮。

    问：怎么加第四个功能？
    答：在 modules 里新建类继承 BaseModule，实现 execute 方法，在 agent.py 的 self.modules 里注册，在 ui/components.py 里加一个新 Tab。
