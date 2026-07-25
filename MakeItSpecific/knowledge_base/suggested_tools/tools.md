---
document_type: "afu_tool_card_collection"
schema_version: "1.0"
created_at: "2026-07-24"
card_count: 20
review_status: "source_reviewed"
---

# 阿福工具知识卡片集（20张）

> 本集收录 Agent 编排、RAG、低代码平台、开发 Agent、LLM 网关、本地模型、向量数据库、Python 工程与浏览器测试工具。所有卡片均记录官方来源，但尚未在阿福环境中执行验证。


<!-- TOOL CARD 01 START -->

---
card_id: "tool-001"
card_type: "tool"
name: "LangGraph"
category: "Agent 编排框架"
source_repository: "langchain-ai/langgraph"
source_url: "https://github.com/langchain-ai/langgraph"
documentation_url: "https://docs.langchain.com/oss/python/langgraph/overview"
repository_popularity_at_review: "高热度官方仓库；实时 Star 以 GitHub 页面为准"
license: "MIT"
reviewed_at: "2026-07-24"
review_status: "source_reviewed"
execution_verified: false
risk_level: "medium"
---

# LangGraph

## 核心结论

用于构建有状态、可恢复、可长期运行的 Agent 工作流。核心价值是用图结构明确节点、状态、分支、循环、人工介入和持久化边界。

## 适用场景

- 需要显式控制 Agent 执行路径
- 存在澄清、执行、检查、反思和重试节点
- 需要保存状态、断点恢复或人工确认
- 复杂流程不能只依赖单次 Prompt

## 触发表达

- 做一个有状态 Agent
- 需要工作流节点和条件分支
- Agent 要支持重试和人工介入
- 长期运行任务
- 构建多阶段任务图

## 主要能力

- 图式工作流与状态管理
- 条件路由、循环和重试
- 检查点与持久化
- 人工介入与中断恢复
- 适配 Python 和 JavaScript 生态

## 限制与不适用情况

- 属于底层编排框架，简单聊天任务可能过度设计
- 状态 Schema、节点职责和终止条件需要提前规划
- 循环与工具调用必须设置硬上限和可观测性

## 使用前应确认

- 任务是否真的需要多节点和持久状态
- 状态字段和节点边界
- 失败重试与终止规则
- 是否需要人工确认或恢复

## 阿福推荐策略

适合阿福自身的 Planner、Clarify、Execute、Checkpoint、Reflector 等状态流。推荐时说明它负责“怎么编排”，不负责自动提供领域知识。

## 风险与执行边界

- **风险等级：** medium
- **当前状态：** 仅完成官方来源审阅，尚未在阿福环境中安装或运行验证。
- **执行原则：** 涉及代码写入、命令执行、外部账号、生产数据、网络公开、凭证或付费资源时，应先获得用户确认。
- **更新原则：** 功能、许可证、价格、版本和兼容性可能变化，正式推荐或实施前应重新核对官方来源。

## 信息源

- **GitHub：** https://github.com/langchain-ai/langgraph
- **官方文档：** https://docs.langchain.com/oss/python/langgraph/overview
- **审阅日期：** 2026-07-24


<!-- TOOL CARD 01 END -->


<!-- TOOL CARD 02 START -->

---
card_id: "tool-002"
card_type: "tool"
name: "LlamaIndex"
category: "RAG 与数据框架"
source_repository: "run-llama/llama_index"
source_url: "https://github.com/run-llama/llama_index"
documentation_url: "https://docs.llamaindex.ai/"
repository_popularity_at_review: "约 50k Star（审阅时仓库级数据）"
license: "MIT"
reviewed_at: "2026-07-24"
review_status: "source_reviewed"
execution_verified: false
risk_level: "medium"
---

# LlamaIndex

## 核心结论

面向 Agent 与 RAG 应用的数据框架，提供数据连接、解析、索引、检索、查询、工作流和集成能力，适合把私有资料接入模型。

## 适用场景

- 构建文档问答或 RAG
- 连接 PDF、API、数据库和文件
- 设计索引、检索器和查询引擎
- 需要父子节点、元数据和多种检索策略

## 触发表达

- 做知识库问答
- 把文档接入大模型
- 设计 RAG 检索
- 文档解析和索引
- 做混合检索

## 主要能力

- 多种数据连接器
- 索引与查询抽象
- 检索、重排和 Agent 集成
- 文档节点与元数据管理
- 支持多种向量库和模型

## 限制与不适用情况

- 集成包较多，版本兼容需要管理
- 高层抽象方便但可能隐藏具体召回行为
- 生产系统仍需自行设计评估、权限和数据更新

## 使用前应确认

- 数据来源和格式
- 分段、元数据与来源关联规则
- 向量库和 Embedding 模型
- 召回评估与更新策略

## 阿福推荐策略

当用户重点是文档接入、检索与知识增强时推荐。对阿福可作为现有三层 RAG 的参考或组件来源，不应在未评估迁移成本时整体替换。

## 风险与执行边界

- **风险等级：** medium
- **当前状态：** 仅完成官方来源审阅，尚未在阿福环境中安装或运行验证。
- **执行原则：** 涉及代码写入、命令执行、外部账号、生产数据、网络公开、凭证或付费资源时，应先获得用户确认。
- **更新原则：** 功能、许可证、价格、版本和兼容性可能变化，正式推荐或实施前应重新核对官方来源。

## 信息源

- **GitHub：** https://github.com/run-llama/llama_index
- **官方文档：** https://docs.llamaindex.ai/
- **审阅日期：** 2026-07-24


<!-- TOOL CARD 02 END -->


<!-- TOOL CARD 03 START -->

---
card_id: "tool-003"
card_type: "tool"
name: "Haystack"
category: "RAG 与 AI 管道"
source_repository: "deepset-ai/haystack"
source_url: "https://github.com/deepset-ai/haystack"
documentation_url: "https://docs.haystack.deepset.ai/"
repository_popularity_at_review: "约 25.4k Star（审阅时仓库级数据）"
license: "Apache-2.0"
reviewed_at: "2026-07-24"
review_status: "source_reviewed"
execution_verified: false
risk_level: "medium"
---

# Haystack

## 核心结论

面向生产级 LLM 应用的模块化编排框架，强调对检索、路由、记忆、生成和组件管道的显式控制。

## 适用场景

- 构建模块化 RAG 管道
- 需要可替换的 Retriever、Ranker 和 Generator
- 实现路由、Agent 或多模态流程
- 重视生产可控性和组件边界

## 触发表达

- 做生产级 RAG
- 搭建检索生成管道
- 需要模块化组件
- 控制路由和记忆
- 替换 Retriever 或 Ranker

## 主要能力

- 组件化 Pipeline
- RAG、Agent 与语义搜索
- 显式路由和数据流
- 多种文档存储与模型集成
- 适合测试独立组件

## 限制与不适用情况

- 需要理解组件输入输出和管道连接
- 简单项目可能比直接调用模型更复杂
- 外部集成版本需要单独维护

## 使用前应确认

- 是否需要组件级替换和评估
- 管道输入输出 Schema
- Document Store 与模型选择
- 部署与可观测性要求

## 阿福推荐策略

适合重视组件化和生产可控性的 RAG 项目。阿福应根据现有架构评估是否采用局部组件，而不是仅因知名度推荐整体迁移。

## 风险与执行边界

- **风险等级：** medium
- **当前状态：** 仅完成官方来源审阅，尚未在阿福环境中安装或运行验证。
- **执行原则：** 涉及代码写入、命令执行、外部账号、生产数据、网络公开、凭证或付费资源时，应先获得用户确认。
- **更新原则：** 功能、许可证、价格、版本和兼容性可能变化，正式推荐或实施前应重新核对官方来源。

## 信息源

- **GitHub：** https://github.com/deepset-ai/haystack
- **官方文档：** https://docs.haystack.deepset.ai/
- **审阅日期：** 2026-07-24


<!-- TOOL CARD 03 END -->


<!-- TOOL CARD 04 START -->

---
card_id: "tool-004"
card_type: "tool"
name: "CrewAI"
category: "多 Agent 协作框架"
source_repository: "crewAIInc/crewAI"
source_url: "https://github.com/crewAIInc/crewAI"
documentation_url: "https://docs.crewai.com/"
repository_popularity_at_review: "约 52k Star（审阅时仓库级数据）"
license: "MIT"
reviewed_at: "2026-07-24"
review_status: "source_reviewed"
execution_verified: false
risk_level: "medium"
---

# CrewAI

## 核心结论

用于组织多个角色化 Agent 协作，可通过 Crews 强调自主协作，通过 Flows 建立事件驱动和更明确的生产流程。

## 适用场景

- 多个角色需要分工协作
- 研究、撰写、审核等任务可明确分角色
- 需要快速搭建多 Agent 原型
- 希望结合自主 Agent 与显式流程

## 触发表达

- 做多智能体团队
- 让几个角色协作
- 研究员和审核员分工
- Crew 或 Flow
- 多 Agent 自动化

## 主要能力

- 角色、任务和工具组织
- Crew 自主协作
- Flow 事件驱动控制
- 多模型和工具集成
- 快速构建多 Agent 原型

## 限制与不适用情况

- 多 Agent 不一定比单 Agent 更好，可能增加成本和不确定性
- 角色边界、共享上下文和终止条件需要验证
- 复杂生产流程仍需日志、权限和失败恢复

## 使用前应确认

- 为什么需要多个 Agent
- 每个角色的独立输入输出
- 成本和最大迭代次数
- 人工确认与失败回退

## 阿福推荐策略

仅在任务确实可拆为互补角色时推荐。阿福应先帮助用户判断单 Agent、工作流还是多 Agent 更合适。

## 风险与执行边界

- **风险等级：** medium
- **当前状态：** 仅完成官方来源审阅，尚未在阿福环境中安装或运行验证。
- **执行原则：** 涉及代码写入、命令执行、外部账号、生产数据、网络公开、凭证或付费资源时，应先获得用户确认。
- **更新原则：** 功能、许可证、价格、版本和兼容性可能变化，正式推荐或实施前应重新核对官方来源。

## 信息源

- **GitHub：** https://github.com/crewAIInc/crewAI
- **官方文档：** https://docs.crewai.com/
- **审阅日期：** 2026-07-24


<!-- TOOL CARD 04 END -->


<!-- TOOL CARD 05 START -->

---
card_id: "tool-005"
card_type: "tool"
name: "Microsoft Agent Framework"
category: "企业级 Agent 框架"
source_repository: "microsoft/agent-framework"
source_url: "https://github.com/microsoft/agent-framework"
documentation_url: "https://learn.microsoft.com/agent-framework/"
repository_popularity_at_review: "微软官方活跃项目；实时 Star 以 GitHub 页面为准"
license: "安装前复核仓库 LICENSE"
reviewed_at: "2026-07-24"
review_status: "source_reviewed"
execution_verified: false
risk_level: "high"
---

# Microsoft Agent Framework

## 核心结论

微软面向 Python 与 .NET 的生产级 Agent 与多 Agent 工作流框架，支持顺序、并发、移交和群组协作等编排模式，并面向本地与云端部署。

## 适用场景

- 团队使用 Python 或 .NET 构建生产 Agent
- 需要与 Azure、Microsoft Foundry 或 GitHub Copilot 生态集成
- 从 AutoGen 迁移
- 需要企业托管、遥测与跨运行时能力

## 触发表达

- 微软 Agent Framework
- 从 AutoGen 迁移
- .NET Agent
- Azure Agent 编排
- 生产级多智能体

## 主要能力

- Python 与 .NET 支持
- 单 Agent 与多 Agent 编排
- 顺序、并发、handoff 和 group 模式
- 多提供商模型支持
- 托管、遥测和企业集成

## 限制与不适用情况

- 生态与 API 仍可能快速演进，需锁定版本
- 与 Azure 服务结合时涉及账号、区域和成本
- 对非微软技术栈可能不是最轻量选择

## 使用前应确认

- Python 还是 .NET
- 是否依赖 Azure 或 Microsoft Foundry
- 部署环境和身份权限
- 是否从 AutoGen 迁移

## 阿福推荐策略

当团队明显处于微软生态或需要 AutoGen 后续方案时推荐。普通个人原型不应因“企业级”标签而默认采用。

## 风险与执行边界

- **风险等级：** high
- **当前状态：** 仅完成官方来源审阅，尚未在阿福环境中安装或运行验证。
- **执行原则：** 涉及代码写入、命令执行、外部账号、生产数据、网络公开、凭证或付费资源时，应先获得用户确认。
- **更新原则：** 功能、许可证、价格、版本和兼容性可能变化，正式推荐或实施前应重新核对官方来源。

## 信息源

- **GitHub：** https://github.com/microsoft/agent-framework
- **官方文档：** https://learn.microsoft.com/agent-framework/
- **审阅日期：** 2026-07-24


<!-- TOOL CARD 05 END -->


<!-- TOOL CARD 06 START -->

---
card_id: "tool-006"
card_type: "tool"
name: "Dify"
category: "低代码 Agent 平台"
source_repository: "langgenius/dify"
source_url: "https://github.com/langgenius/dify"
documentation_url: "https://docs.dify.ai/"
repository_popularity_at_review: "约 145k+ Star（审阅时仓库级数据）"
license: "Dify Open Source License（基于 Apache-2.0 并含附加条件）"
reviewed_at: "2026-07-24"
review_status: "source_reviewed"
execution_verified: false
risk_level: "high"
---

# Dify

## 核心结论

面向 Agent 与 LLM 工作流开发的可视化平台，集成模型、Prompt、知识库、工具、工作流、调试和应用发布。

## 适用场景

- 快速搭建可视化 LLM 应用
- 非纯代码团队设计工作流
- 组合模型、知识库与工具
- 需要管理界面和应用发布能力

## 触发表达

- 用 Dify 搭 Agent
- 低代码工作流
- 可视化 RAG
- 快速发布 AI 应用
- 管理 Prompt 和知识库

## 主要能力

- 可视化工作流与 Agent 构建
- 模型和工具集成
- 知识库与 RAG
- 调试、日志和应用发布
- 自托管与云服务选项

## 限制与不适用情况

- 许可证含附加条件，商用前需核对
- 平台抽象可能限制深度定制
- 插件、沙箱和公开服务需要安全配置

## 使用前应确认

- 云端还是自托管
- 许可证和商业用途
- 模型密钥与数据存储位置
- 是否允许外部用户运行 Agent

## 阿福推荐策略

适合需要快速验证产品工作流或由非纯代码成员参与搭建的场景。高定制项目应先评估平台边界。

## 风险与执行边界

- **风险等级：** high
- **当前状态：** 仅完成官方来源审阅，尚未在阿福环境中安装或运行验证。
- **执行原则：** 涉及代码写入、命令执行、外部账号、生产数据、网络公开、凭证或付费资源时，应先获得用户确认。
- **更新原则：** 功能、许可证、价格、版本和兼容性可能变化，正式推荐或实施前应重新核对官方来源。

## 信息源

- **GitHub：** https://github.com/langgenius/dify
- **官方文档：** https://docs.dify.ai/
- **审阅日期：** 2026-07-24


<!-- TOOL CARD 06 END -->


<!-- TOOL CARD 07 START -->

---
card_id: "tool-007"
card_type: "tool"
name: "Flowise"
category: "可视化 Agent 构建"
source_repository: "FlowiseAI/Flowise"
source_url: "https://github.com/FlowiseAI/Flowise"
documentation_url: "https://docs.flowiseai.com/"
repository_popularity_at_review: "约 53k Star（审阅时仓库级数据）"
license: "Apache-2.0"
reviewed_at: "2026-07-24"
review_status: "source_reviewed"
execution_verified: false
risk_level: "high"
---

# Flowise

## 核心结论

通过可视化节点构建 Agent、聊天流与 AI 工作流，适合快速连接模型、向量库、工具和自定义逻辑。

## 适用场景

- 快速验证 Agent 流程
- 以节点方式连接模型和检索组件
- 演示聊天机器人或多步骤工作流
- 需要低代码但仍保留扩展能力

## 触发表达

- 用 Flowise 搭流程
- 可视化连接 LLM
- 拖拽式 Agent
- 快速做聊天机器人
- 低代码 RAG

## 主要能力

- 节点式工作流编辑
- 模型、向量库与工具集成
- 聊天流和 Agent 流
- API 与嵌入式组件
- 多种部署选项

## 限制与不适用情况

- 复杂流程可能变成难维护的节点图
- 公开部署需配置认证和密钥保护
- 生产可观测性、版本管理和测试仍需补充

## 使用前应确认

- 原型还是生产系统
- 部署与访问控制
- 模型密钥存储
- 节点版本与导出备份

## 阿福推荐策略

当用户需要快速可视化验证流程时推荐；若逻辑复杂且要求严格测试，应提醒同步保留代码化或版本化方案。

## 风险与执行边界

- **风险等级：** high
- **当前状态：** 仅完成官方来源审阅，尚未在阿福环境中安装或运行验证。
- **执行原则：** 涉及代码写入、命令执行、外部账号、生产数据、网络公开、凭证或付费资源时，应先获得用户确认。
- **更新原则：** 功能、许可证、价格、版本和兼容性可能变化，正式推荐或实施前应重新核对官方来源。

## 信息源

- **GitHub：** https://github.com/FlowiseAI/Flowise
- **官方文档：** https://docs.flowiseai.com/
- **审阅日期：** 2026-07-24


<!-- TOOL CARD 07 END -->


<!-- TOOL CARD 08 START -->

---
card_id: "tool-008"
card_type: "tool"
name: "n8n"
category: "工作流自动化平台"
source_repository: "n8n-io/n8n"
source_url: "https://github.com/n8n-io/n8n"
documentation_url: "https://docs.n8n.io/"
repository_popularity_at_review: "约 190k Star（审阅时仓库级数据）"
license: "Fair-code / Sustainable Use 条款；商业与托管用途需复核"
reviewed_at: "2026-07-24"
review_status: "source_reviewed"
execution_verified: false
risk_level: "critical"
---

# n8n

## 核心结论

可视化自动化平台，支持大量第三方集成、代码节点、AI 工作流、人工审批以及云端或自托管部署。

## 适用场景

- 连接邮件、表格、数据库、Webhook 和 SaaS
- 构建定时或事件驱动自动化
- 把 AI 步骤嵌入业务流程
- 需要人工审批和多系统集成

## 触发表达

- 自动处理邮件
- 连接多个系统
- 做定时工作流
- Webhook 自动化
- 用 n8n 串联 Agent

## 主要能力

- 大量第三方集成
- 可视化流程与代码节点
- Webhook、定时和事件触发
- AI 节点与多模型
- 自托管、权限与审计能力

## 限制与不适用情况

- Fair-code 许可并非传统宽松开源许可
- 凭证和业务数据安全是核心风险
- 流程过大时需要拆分、版本管理和故障恢复

## 使用前应确认

- 触发方式和运行频率
- 涉及哪些账号与凭证
- 写操作和人工审批点
- 失败重试、幂等和审计要求

## 阿福推荐策略

当用户目标是跨系统自动化而不是单纯聊天时推荐。涉及发送、删除、支付或生产数据时必须先确认。

## 风险与执行边界

- **风险等级：** critical
- **当前状态：** 仅完成官方来源审阅，尚未在阿福环境中安装或运行验证。
- **执行原则：** 涉及代码写入、命令执行、外部账号、生产数据、网络公开、凭证或付费资源时，应先获得用户确认。
- **更新原则：** 功能、许可证、价格、版本和兼容性可能变化，正式推荐或实施前应重新核对官方来源。

## 信息源

- **GitHub：** https://github.com/n8n-io/n8n
- **官方文档：** https://docs.n8n.io/
- **审阅日期：** 2026-07-24


<!-- TOOL CARD 08 END -->


<!-- TOOL CARD 09 START -->

---
card_id: "tool-009"
card_type: "tool"
name: "OpenHands"
category: "软件开发 Agent"
source_repository: "All-Hands-AI/OpenHands"
source_url: "https://github.com/All-Hands-AI/OpenHands"
documentation_url: "https://docs.openhands.dev/"
repository_popularity_at_review: "约 68.9k Star（审阅时仓库级数据）"
license: "核心 MIT；enterprise 目录含单独条款"
reviewed_at: "2026-07-24"
review_status: "source_reviewed"
execution_verified: false
risk_level: "critical"
---

# OpenHands

## 核心结论

提供软件开发 Agent SDK、CLI、本地 GUI 和云服务，可修改代码、运行命令、浏览网页和调用 API。

## 适用场景

- 需要较自主的软件开发 Agent
- 让 Agent 在沙箱中修改和运行项目
- 通过 CLI 或本地 GUI 完成开发任务
- 批量或长时间软件工程任务

## 触发表达

- 让 Agent 自己改项目
- 自动运行代码和命令
- 使用 OpenHands
- 软件开发智能体
- 让 AI 完成一个 Issue

## 主要能力

- 代码修改与命令执行
- 浏览器和 API 使用
- SDK、CLI 与 GUI
- 本地 Docker 与云端运行
- 支持多种模型

## 限制与不适用情况

- 自主权限高，可能修改文件、执行命令和访问网络
- 必须在隔离环境、版本控制和权限限制下运行
- 结果不能跳过测试与人工代码审查

## 使用前应确认

- 允许访问的仓库和目录
- 是否使用沙箱或容器
- 网络与凭证权限
- 可执行命令范围和回滚方式

## 阿福推荐策略

仅在任务契约清晰、环境隔离且用户接受自主执行时推荐。阿福应先完成范围、验收、风险和回滚确认。

## 风险与执行边界

- **风险等级：** critical
- **当前状态：** 仅完成官方来源审阅，尚未在阿福环境中安装或运行验证。
- **执行原则：** 涉及代码写入、命令执行、外部账号、生产数据、网络公开、凭证或付费资源时，应先获得用户确认。
- **更新原则：** 功能、许可证、价格、版本和兼容性可能变化，正式推荐或实施前应重新核对官方来源。

## 信息源

- **GitHub：** https://github.com/All-Hands-AI/OpenHands
- **官方文档：** https://docs.openhands.dev/
- **审阅日期：** 2026-07-24


<!-- TOOL CARD 09 END -->


<!-- TOOL CARD 10 START -->

---
card_id: "tool-010"
card_type: "tool"
name: "Aider"
category: "终端 AI 编程"
source_repository: "Aider-AI/aider"
source_url: "https://github.com/Aider-AI/aider"
documentation_url: "https://aider.chat/docs/"
repository_popularity_at_review: "约 45k Star（审阅时仓库级数据）"
license: "Apache-2.0"
reviewed_at: "2026-07-24"
review_status: "source_reviewed"
execution_verified: false
risk_level: "high"
---

# Aider

## 核心结论

运行在终端中的 AI 结对编程工具，可理解代码库映射、编辑多种语言，并通过 Git 提交帮助用户查看、撤销和管理变更。

## 适用场景

- 在现有代码库中进行有边界的修改
- 偏好终端和 Git 工作流
- 需要模型理解较大代码库
- 希望每次改动都能 diff 和回滚

## 触发表达

- 用终端让 AI 改代码
- Aider 修改项目
- 自动提交 Git
- 结对编程
- 让模型理解整个代码库

## 主要能力

- 代码库映射
- 多文件编辑
- 多模型支持
- Git 自动提交和撤销
- 支持图像和网页上下文

## 限制与不适用情况

- 自动提交不代表代码正确
- 错误任务描述可能造成大范围修改
- 模型和 API 成本需管理，敏感仓库需谨慎

## 使用前应确认

- 工作分支和干净的 Git 状态
- 允许修改的文件范围
- 测试命令与验收标准
- 模型、成本和凭证

## 阿福推荐策略

当用户明确要在代码库中落地修改且熟悉 Git 时推荐。阿福应先生成可执行任务说明，并建议在独立分支运行。

## 风险与执行边界

- **风险等级：** high
- **当前状态：** 仅完成官方来源审阅，尚未在阿福环境中安装或运行验证。
- **执行原则：** 涉及代码写入、命令执行、外部账号、生产数据、网络公开、凭证或付费资源时，应先获得用户确认。
- **更新原则：** 功能、许可证、价格、版本和兼容性可能变化，正式推荐或实施前应重新核对官方来源。

## 信息源

- **GitHub：** https://github.com/Aider-AI/aider
- **官方文档：** https://aider.chat/docs/
- **审阅日期：** 2026-07-24


<!-- TOOL CARD 10 END -->


<!-- TOOL CARD 11 START -->

---
card_id: "tool-011"
card_type: "tool"
name: "Continue"
category: "AI 代码检查与 IDE 工具"
source_repository: "continuedev/continue"
source_url: "https://github.com/continuedev/continue"
documentation_url: "https://docs.continue.dev/"
repository_popularity_at_review: "约 33.7k Star（审阅时仓库级数据）"
license: "Apache-2.0"
reviewed_at: "2026-07-24"
review_status: "source_reviewed"
execution_verified: false
risk_level: "high"
---

# Continue

## 核心结论

提供可版本控制的 AI Checks 与 CLI，可在 Pull Request 中运行 Markdown 定义的检查规则，并支持 IDE 相关开发工作流。

## 适用场景

- 将安全、风格或架构规则变成 PR 检查
- 在 CI 中执行 AI 审查
- 希望检查规则与代码库一起版本控制
- 构建组织级代码审核标准

## 触发表达

- 让 AI 检查每个 PR
- 写一个安全审查 Check
- 在 CI 里跑 Agent
- Continue CLI
- 代码规则自动检查

## 主要能力

- Markdown 定义检查规则
- PR 状态检查与建议 Diff
- CLI 与 CI 集成
- 规则随代码库版本控制
- 适合安全、规范和架构审查

## 限制与不适用情况

- AI 检查可能误报或漏报
- 不能替代静态分析、测试与人工审查
- CI 中调用模型会带来成本、隐私和稳定性问题

## 使用前应确认

- 检查规则和通过标准
- 模型与数据传输位置
- CI 权限和 Secret 管理
- 检查失败是否阻断合并

## 阿福推荐策略

当用户希望把工程规范变成持续验证机制时推荐。先从少量高价值检查开始，避免用模糊规则阻断整个团队。

## 风险与执行边界

- **风险等级：** high
- **当前状态：** 仅完成官方来源审阅，尚未在阿福环境中安装或运行验证。
- **执行原则：** 涉及代码写入、命令执行、外部账号、生产数据、网络公开、凭证或付费资源时，应先获得用户确认。
- **更新原则：** 功能、许可证、价格、版本和兼容性可能变化，正式推荐或实施前应重新核对官方来源。

## 信息源

- **GitHub：** https://github.com/continuedev/continue
- **官方文档：** https://docs.continue.dev/
- **审阅日期：** 2026-07-24


<!-- TOOL CARD 11 END -->


<!-- TOOL CARD 12 START -->

---
card_id: "tool-012"
card_type: "tool"
name: "LiteLLM"
category: "LLM 网关"
source_repository: "BerriAI/litellm"
source_url: "https://github.com/BerriAI/litellm"
documentation_url: "https://docs.litellm.ai/"
repository_popularity_at_review: "约 46k Star（审阅时仓库级数据）"
license: "开源与商业功能并存；部署前复核当前 LICENSE"
reviewed_at: "2026-07-24"
review_status: "source_reviewed"
execution_verified: false
risk_level: "critical"
---

# LiteLLM

## 核心结论

通过统一接口调用多家模型提供商，可作为 Python SDK 或集中式 AI Gateway，支持路由、负载均衡、成本跟踪、日志和 Guardrails。

## 适用场景

- 同时接入 OpenAI、Anthropic、Gemini、Bedrock 等模型
- 统一模型调用接口
- 做重试、路由、限额和成本管理
- 团队需要集中管理模型密钥

## 触发表达

- 统一多个模型 API
- 做 LLM Gateway
- 模型故障切换
- 统计模型成本
- 集中管理 API Key

## 主要能力

- 兼容 OpenAI 风格接口
- 多提供商模型路由
- 重试与负载均衡
- 成本、日志和限额
- 集中式代理与团队管理

## 限制与不适用情况

- 网关成为关键基础设施和潜在单点
- 日志可能包含敏感 Prompt 或响应
- 不同模型能力并不能被统一接口完全抹平

## 使用前应确认

- 使用 SDK 还是 Proxy
- 密钥托管和访问控制
- 日志脱敏与保留周期
- 路由、预算和故障回退策略

## 阿福推荐策略

当用户需要在多个模型间切换或做统一治理时推荐。单模型小项目不必为了抽象而额外增加网关。

## 风险与执行边界

- **风险等级：** critical
- **当前状态：** 仅完成官方来源审阅，尚未在阿福环境中安装或运行验证。
- **执行原则：** 涉及代码写入、命令执行、外部账号、生产数据、网络公开、凭证或付费资源时，应先获得用户确认。
- **更新原则：** 功能、许可证、价格、版本和兼容性可能变化，正式推荐或实施前应重新核对官方来源。

## 信息源

- **GitHub：** https://github.com/BerriAI/litellm
- **官方文档：** https://docs.litellm.ai/
- **审阅日期：** 2026-07-24


<!-- TOOL CARD 12 END -->


<!-- TOOL CARD 13 START -->

---
card_id: "tool-013"
card_type: "tool"
name: "Ollama"
category: "本地模型运行"
source_repository: "ollama/ollama"
source_url: "https://github.com/ollama/ollama"
documentation_url: "https://docs.ollama.com/"
repository_popularity_at_review: "约 172k Star（审阅时仓库级数据）"
license: "MIT"
reviewed_at: "2026-07-24"
review_status: "source_reviewed"
execution_verified: false
risk_level: "medium"
---

# Ollama

## 核心结论

在本地下载、运行和服务多种开放模型，并提供命令行、HTTP API、Python/JavaScript 客户端和多种 Agent 集成。

## 适用场景

- 本地运行模型和保护数据
- 离线或内网原型
- 测试不同开放模型
- 为 Agent 提供本地推理服务

## 触发表达

- 本地跑大模型
- 不用云端 API
- Ollama 启动模型
- 离线模型
- 把本地模型接到 Agent

## 主要能力

- 模型下载与运行
- 本地 HTTP API
- Python 和 JavaScript 库
- 多种模型与 Agent 集成
- Docker 和跨平台支持

## 限制与不适用情况

- 性能和可运行模型受硬件限制
- 本地运行不自动等于安全，仍需保护端口和模型数据
- 模型质量、上下文长度和许可证各不相同

## 使用前应确认

- CPU、GPU、内存和磁盘
- 模型许可证与用途
- 是否暴露网络端口
- 并发、延迟和上下文需求

## 阿福推荐策略

当隐私、离线或成本是核心约束时推荐。阿福应先判断硬件和模型能力是否满足任务，而不是默认本地模型更合适。

## 风险与执行边界

- **风险等级：** medium
- **当前状态：** 仅完成官方来源审阅，尚未在阿福环境中安装或运行验证。
- **执行原则：** 涉及代码写入、命令执行、外部账号、生产数据、网络公开、凭证或付费资源时，应先获得用户确认。
- **更新原则：** 功能、许可证、价格、版本和兼容性可能变化，正式推荐或实施前应重新核对官方来源。

## 信息源

- **GitHub：** https://github.com/ollama/ollama
- **官方文档：** https://docs.ollama.com/
- **审阅日期：** 2026-07-24


<!-- TOOL CARD 13 END -->


<!-- TOOL CARD 14 START -->

---
card_id: "tool-014"
card_type: "tool"
name: "Qdrant"
category: "向量数据库"
source_repository: "qdrant/qdrant"
source_url: "https://github.com/qdrant/qdrant"
documentation_url: "https://qdrant.tech/documentation/"
repository_popularity_at_review: "约 31.6k Star（审阅时仓库级数据）"
license: "Apache-2.0"
reviewed_at: "2026-07-24"
review_status: "source_reviewed"
execution_verified: false
risk_level: "high"
---

# Qdrant

## 核心结论

以 Rust 编写的向量搜索引擎和数据库，支持向量、Payload、过滤、索引和托管云，适合语义检索、推荐和 RAG。

## 适用场景

- 需要独立向量数据库
- 向量检索伴随复杂元数据过滤
- RAG 数据规模增长
- 需要云端或自托管向量服务

## 触发表达

- 选择向量数据库
- Qdrant 做 RAG
- 向量过滤
- 大规模语义检索
- 部署向量服务

## 主要能力

- 向量存储与相似度搜索
- Payload 和结构化过滤
- 多种距离和索引能力
- 客户端与集成生态
- 自托管和云服务

## 限制与不适用情况

- 引入独立服务会增加部署和备份成本
- 索引参数、分片和过滤设计需基于数据测试
- 向量库不能解决分段和知识质量问题

## 使用前应确认

- 数据规模和查询量
- 向量维度与距离方式
- 过滤字段和多租户要求
- 备份、权限和部署方式

## 阿福推荐策略

当现有数据库无法满足独立向量检索规模或过滤需求时推荐。对小项目可先评估 pgvector 或嵌入式方案。

## 风险与执行边界

- **风险等级：** high
- **当前状态：** 仅完成官方来源审阅，尚未在阿福环境中安装或运行验证。
- **执行原则：** 涉及代码写入、命令执行、外部账号、生产数据、网络公开、凭证或付费资源时，应先获得用户确认。
- **更新原则：** 功能、许可证、价格、版本和兼容性可能变化，正式推荐或实施前应重新核对官方来源。

## 信息源

- **GitHub：** https://github.com/qdrant/qdrant
- **官方文档：** https://qdrant.tech/documentation/
- **审阅日期：** 2026-07-24


<!-- TOOL CARD 14 END -->


<!-- TOOL CARD 15 START -->

---
card_id: "tool-015"
card_type: "tool"
name: "Chroma"
category: "向量与检索基础设施"
source_repository: "chroma-core/chroma"
source_url: "https://github.com/chroma-core/chroma"
documentation_url: "https://docs.trychroma.com/"
repository_popularity_at_review: "约 28.2k Star（审阅时仓库级数据）"
license: "Apache-2.0（部署前复核仓库 LICENSE）"
reviewed_at: "2026-07-24"
review_status: "source_reviewed"
execution_verified: false
risk_level: "medium"
---

# Chroma

## 核心结论

面向 AI 应用的检索基础设施，提供向量存储、元数据、查询和本地开发体验，常用于快速构建 RAG 原型。

## 适用场景

- 快速构建本地 RAG 原型
- 在 Python 应用中嵌入向量存储
- 需要简单的集合、文档和元数据查询
- 从实验阶段验证检索效果

## 触发表达

- 快速做向量库
- 本地 RAG 原型
- 使用 Chroma
- 存 Embedding
- 轻量语义检索

## 主要能力

- 本地和服务化使用
- 集合与文档管理
- 向量和元数据查询
- 常见框架集成
- 上手成本较低

## 限制与不适用情况

- 生产规模、并发、备份与运维需要单独评估
- 版本升级和持久化兼容需测试
- 不能因易用而跳过评估与来源管理

## 使用前应确认

- 原型还是生产环境
- 持久化和备份要求
- 数据规模与并发
- 元数据过滤和多租户需求

## 阿福推荐策略

适合快速验证小中型 RAG。进入生产前应通过真实数据评估容量、稳定性和迁移方案。

## 风险与执行边界

- **风险等级：** medium
- **当前状态：** 仅完成官方来源审阅，尚未在阿福环境中安装或运行验证。
- **执行原则：** 涉及代码写入、命令执行、外部账号、生产数据、网络公开、凭证或付费资源时，应先获得用户确认。
- **更新原则：** 功能、许可证、价格、版本和兼容性可能变化，正式推荐或实施前应重新核对官方来源。

## 信息源

- **GitHub：** https://github.com/chroma-core/chroma
- **官方文档：** https://docs.trychroma.com/
- **审阅日期：** 2026-07-24


<!-- TOOL CARD 15 END -->


<!-- TOOL CARD 16 START -->

---
card_id: "tool-016"
card_type: "tool"
name: "pgvector"
category: "PostgreSQL 向量扩展"
source_repository: "pgvector/pgvector"
source_url: "https://github.com/pgvector/pgvector"
documentation_url: "https://github.com/pgvector/pgvector"
repository_popularity_at_review: "约 21.7k Star（审阅时仓库级数据）"
license: "PostgreSQL License"
reviewed_at: "2026-07-24"
review_status: "source_reviewed"
execution_verified: false
risk_level: "high"
---

# pgvector

## 核心结论

为 PostgreSQL 增加向量类型和精确/近似相似度搜索，使向量与业务数据、事务、JOIN、备份和权限体系共存。

## 适用场景

- 项目已经使用 PostgreSQL
- 向量数据需与业务表关联
- 希望减少独立基础设施
- 中小规模 RAG 与结构化过滤并存

## 触发表达

- Postgres 做向量库
- 使用 PGVector
- 向量和业务数据一起存
- SQL 过滤加语义检索
- 减少一个数据库

## 主要能力

- 向量类型和多种距离
- 精确与近似搜索
- 支持稠密、稀疏和二进制向量
- 利用 PostgreSQL 事务、JOIN 和备份
- 兼容多语言 Postgres 客户端

## 限制与不适用情况

- 大规模高并发向量检索需仔细调优
- 索引、过滤和查询计划需要数据库能力
- 与业务库共存可能带来资源竞争

## 使用前应确认

- PostgreSQL 版本和托管商支持
- 向量规模、索引和查询模式
- 业务库资源隔离
- 迁移、备份和扩展安装权限

## 阿福推荐策略

当项目已有 PostgreSQL 且规模适中时优先作为简单方案评估。阿福现有 PGVector 设计可继续使用，但需通过真实召回测试确认。

## 风险与执行边界

- **风险等级：** high
- **当前状态：** 仅完成官方来源审阅，尚未在阿福环境中安装或运行验证。
- **执行原则：** 涉及代码写入、命令执行、外部账号、生产数据、网络公开、凭证或付费资源时，应先获得用户确认。
- **更新原则：** 功能、许可证、价格、版本和兼容性可能变化，正式推荐或实施前应重新核对官方来源。

## 信息源

- **GitHub：** https://github.com/pgvector/pgvector
- **官方文档：** https://github.com/pgvector/pgvector
- **审阅日期：** 2026-07-24


<!-- TOOL CARD 16 END -->


<!-- TOOL CARD 17 START -->

---
card_id: "tool-017"
card_type: "tool"
name: "Milvus"
category: "分布式向量数据库"
source_repository: "milvus-io/milvus"
source_url: "https://github.com/milvus-io/milvus"
documentation_url: "https://milvus.io/docs"
repository_popularity_at_review: "约 44.5k Star（审阅时仓库级数据）"
license: "Apache-2.0"
reviewed_at: "2026-07-24"
review_status: "source_reviewed"
execution_verified: false
risk_level: "high"
---

# Milvus

## 核心结论

面向大规模向量近邻检索的云原生数据库，支持水平扩展、实时更新、单机模式和轻量版，适合海量文本、图像及多模态向量。

## 适用场景

- 数据量达到大规模或需要分布式扩展
- 高吞吐向量检索
- 多模态搜索与推荐
- 需要 Standalone、分布式或托管云选项

## 触发表达

- 亿级向量检索
- 选择 Milvus
- 分布式向量库
- 多模态向量搜索
- 高吞吐 ANN

## 主要能力

- 大规模 ANN 搜索
- 水平扩展与实时更新
- 多种索引与硬件优化
- Standalone、Milvus Lite 和云选项
- 多语言 SDK

## 限制与不适用情况

- 分布式部署和运维成本较高
- 小项目可能明显过度设计
- 索引和资源参数必须通过基准测试确定

## 使用前应确认

- 实际向量数量和增长
- 吞吐、延迟与一致性要求
- 单机还是 Kubernetes
- 团队运维能力和预算

## 阿福推荐策略

仅在规模和性能指标确实需要分布式向量库时推荐，不能因 Star 高就用于小型知识库。

## 风险与执行边界

- **风险等级：** high
- **当前状态：** 仅完成官方来源审阅，尚未在阿福环境中安装或运行验证。
- **执行原则：** 涉及代码写入、命令执行、外部账号、生产数据、网络公开、凭证或付费资源时，应先获得用户确认。
- **更新原则：** 功能、许可证、价格、版本和兼容性可能变化，正式推荐或实施前应重新核对官方来源。

## 信息源

- **GitHub：** https://github.com/milvus-io/milvus
- **官方文档：** https://milvus.io/docs
- **审阅日期：** 2026-07-24


<!-- TOOL CARD 17 END -->


<!-- TOOL CARD 18 START -->

---
card_id: "tool-018"
card_type: "tool"
name: "Weaviate"
category: "混合搜索向量数据库"
source_repository: "weaviate/weaviate"
source_url: "https://github.com/weaviate/weaviate"
documentation_url: "https://weaviate.io/developers/weaviate"
repository_popularity_at_review: "约 16.2k Star（审阅时仓库级数据）"
license: "BSD-3-Clause"
reviewed_at: "2026-07-24"
review_status: "source_reviewed"
execution_verified: false
risk_level: "high"
---

# Weaviate

## 核心结论

云原生向量数据库，支持对象与向量、结构化过滤、关键词与向量混合搜索、RAG、重排、多租户、复制和权限控制。

## 适用场景

- 需要混合搜索和结构化过滤
- 希望数据库集成自动向量化模型
- 多租户 RAG 或语义搜索
- 需要云服务和企业权限能力

## 触发表达

- 混合搜索向量库
- Weaviate 做 RAG
- BM25 加向量检索
- 多租户向量数据库
- 自动向量化

## 主要能力

- 向量与对象存储
- 混合检索和过滤
- 自动或外部向量化
- RAG 与重排集成
- 多租户、复制和 RBAC

## 限制与不适用情况

- 集成功能多也意味着配置和锁定风险
- 自动向量化需要管理外部模型成本与数据传输
- 部署模式与商业服务条款需分别核对

## 使用前应确认

- 自动向量化还是自带 Embedding
- 混合检索权重与评估
- 多租户和权限
- 云端或自托管

## 阿福推荐策略

当用户明确需要混合搜索、多租户或集成式向量化时推荐；普通单机 RAG 应先选择更简单方案。

## 风险与执行边界

- **风险等级：** high
- **当前状态：** 仅完成官方来源审阅，尚未在阿福环境中安装或运行验证。
- **执行原则：** 涉及代码写入、命令执行、外部账号、生产数据、网络公开、凭证或付费资源时，应先获得用户确认。
- **更新原则：** 功能、许可证、价格、版本和兼容性可能变化，正式推荐或实施前应重新核对官方来源。

## 信息源

- **GitHub：** https://github.com/weaviate/weaviate
- **官方文档：** https://weaviate.io/developers/weaviate
- **审阅日期：** 2026-07-24


<!-- TOOL CARD 18 END -->


<!-- TOOL CARD 19 START -->

---
card_id: "tool-019"
card_type: "tool"
name: "uv"
category: "Python 项目与依赖管理"
source_repository: "astral-sh/uv"
source_url: "https://github.com/astral-sh/uv"
documentation_url: "https://docs.astral.sh/uv/"
repository_popularity_at_review: "高热度官方仓库；实时 Star 以 GitHub 页面为准"
license: "Apache-2.0 OR MIT"
reviewed_at: "2026-07-24"
review_status: "source_reviewed"
execution_verified: false
risk_level: "low"
---

# uv

## 核心结论

使用 Rust 编写的高速 Python 包和项目管理工具，统一覆盖 Python 版本、虚拟环境、依赖、锁文件、脚本、工具运行和发布流程。

## 适用场景

- 新建或长期维护 Python 项目
- 需要可复现依赖和统一锁文件
- 替代 pip、pip-tools、virtualenv 或部分 Poetry 工作流
- 在 CI 中加速依赖安装

## 触发表达

- Python 项目怎么管理依赖
- 使用 uv
- 创建虚拟环境
- 生成锁文件
- 加速 pip 安装

## 主要能力

- 项目初始化与依赖管理
- 通用锁文件
- Python 版本安装
- 运行脚本和命令行工具
- 兼容部分 pip 工作流
- 速度快且适合 CI

## 限制与不适用情况

- 已有 Poetry、Conda 或组织规范时不应强制迁移
- 迁移依赖和构建配置需要测试
- 新功能和审计能力应锁定版本后使用

## 使用前应确认

- 新项目还是迁移项目
- 是否存在 Conda 或系统级依赖
- Python 版本范围
- CI、发布和锁文件要求

## 阿福推荐策略

长期维护的普通 Python 项目可作为优先建议；临时单文件脚本或已有稳定工具链时不必强推。

## 风险与执行边界

- **风险等级：** low
- **当前状态：** 仅完成官方来源审阅，尚未在阿福环境中安装或运行验证。
- **执行原则：** 涉及代码写入、命令执行、外部账号、生产数据、网络公开、凭证或付费资源时，应先获得用户确认。
- **更新原则：** 功能、许可证、价格、版本和兼容性可能变化，正式推荐或实施前应重新核对官方来源。

## 信息源

- **GitHub：** https://github.com/astral-sh/uv
- **官方文档：** https://docs.astral.sh/uv/
- **审阅日期：** 2026-07-24


<!-- TOOL CARD 19 END -->


<!-- TOOL CARD 20 START -->

---
card_id: "tool-020"
card_type: "tool"
name: "Playwright"
category: "浏览器自动化与 E2E 测试"
source_repository: "microsoft/playwright"
source_url: "https://github.com/microsoft/playwright"
documentation_url: "https://playwright.dev/"
repository_popularity_at_review: "约 91k Star（审阅时仓库级数据）"
license: "Apache-2.0"
reviewed_at: "2026-07-24"
review_status: "source_reviewed"
execution_verified: false
risk_level: "medium"
---

# Playwright

## 核心结论

统一驱动 Chromium、Firefox 和 WebKit 的浏览器自动化与测试框架，提供 E2E 测试、CLI、MCP、断言、隔离和多语言支持。

## 适用场景

- 测试网页关键路径
- 跨浏览器验证
- 自动化表单、路由和截图
- 让编码 Agent 在真实浏览器中检查页面
- 构建回归测试

## 触发表达

- 写端到端测试
- 浏览器自动化
- 测试 Chromium Firefox WebKit
- Playwright MCP
- 验证网页交互

## 主要能力

- 跨浏览器自动化
- 自动等待和 Web-first Assertions
- 测试隔离、追踪和截图
- CLI、MCP 和 VS Code 集成
- 支持 JavaScript、Python、.NET 和 Java

## 限制与不适用情况

- 端到端测试较慢且需要维护选择器和环境
- 第三方验证码、支付和真实账号需特殊处理
- 不能只依赖 E2E，仍需单元与集成测试

## 使用前应确认

- 关键用户路径与预期结果
- 目标浏览器和设备
- 测试数据、账号和环境
- CI 并发与失败证据保留

## 阿福推荐策略

当网页进入验证阶段或需要复现交互问题时优先推荐。阿福应先整理测试用例和验收标准，再生成或运行脚本。

## 风险与执行边界

- **风险等级：** medium
- **当前状态：** 仅完成官方来源审阅，尚未在阿福环境中安装或运行验证。
- **执行原则：** 涉及代码写入、命令执行、外部账号、生产数据、网络公开、凭证或付费资源时，应先获得用户确认。
- **更新原则：** 功能、许可证、价格、版本和兼容性可能变化，正式推荐或实施前应重新核对官方来源。

## 信息源

- **GitHub：** https://github.com/microsoft/playwright
- **官方文档：** https://playwright.dev/
- **审阅日期：** 2026-07-24


<!-- TOOL CARD 20 END -->
