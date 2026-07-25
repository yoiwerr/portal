---
document_type: "afu_skill_card_collection"
schema_version: "1.0"
created_at: "2026-07-23"
card_count: 20
review_status: "source_reviewed"
---

# 阿福 Skill 知识卡片集（20张）

> 说明：本集从 Anthropic 与 Vercel 官方高 Star 仓库中筛选。Star 为仓库级数据，不代表单个 Skill 的安装量或质量。卡片仅完成来源审阅，尚未在阿福环境中执行验证。


<!-- CARD 01 START -->

---
card_id: "skill-001"
card_type: "skill"
name: "frontend-design"
display_name: "Frontend Design"
category: "前端设计"
source_owner: "anthropics"
source_repository: "anthropics/skills"
source_repository_stars_at_review: "约 164k（仓库级 Star，不代表单个 Skill）"
source_url: "https://github.com/anthropics/skills/tree/main/skills/frontend-design"
source_skill_file: "https://github.com/anthropics/skills/blob/main/skills/frontend-design/SKILL.md"
license: "以对应技能目录中的 LICENSE.txt 为准"
reviewed_at: "2026-07-23"
review_status: "source_reviewed"
execution_verified: false
risk_level: "low"
tags:
  - "前端设计"
  - "agent-skill"
  - "anthropics"
  - "frontend-design"
---

# Frontend Design

## 核心结论

为新建或重塑界面提供具有明确视觉立场的设计指导，强调从产品主题、受众与页面任务出发，建立配色、字体、布局和标志性视觉元素，避免模板化的“AI 默认风格”。

## 适用场景

- 设计或重构网页、应用界面和落地页
- 已有页面能用但缺少辨识度
- 需要先形成视觉方向、设计令牌和线框草图
- 需要兼顾响应式、键盘焦点和减少动画偏好

## 触发表达

- 重新设计这个页面
- 做一个有辨识度的前端
- 不要像模板
- 优化 UI 视觉
- 确定配色、字体和布局

## 主要能力

- 先明确具体主题、受众与页面单一目标
- 输出紧凑的颜色、字体、布局和 signature 元素方案
- 在编码前自检是否落入常见模板风格
- 指导界面文案、空状态、错误状态与动作命名
- 强调移动端、焦点可见和 reduced-motion 等质量底线

## 限制与不适用情况

- 它偏向视觉方向和实现原则，不代替完整的用户研究或可用性测试
- 如果用户已有严格品牌规范，应以用户规范为最高优先级
- 大胆设计仍需约束在产品目标内，不能为了独特而牺牲可用性

## 使用前应确认

- 目标用户是谁
- 页面最重要的单一任务是什么
- 已有品牌、颜色、字体或禁用风格
- 是在现有代码上改造还是新建

## 阿福推荐策略

当用户需要生成或改造前端界面且视觉要求较高时推荐。表达方式：建议使用 Frontend Design Skill，因为它会在编码前先确定视觉方向并避免模板化；阿福可先帮用户整理页面目标、布局比例、品牌约束和验收标准。

## 兼容性与安装

- **兼容性说明：** 原生面向 Claude；采用 Agent Skills 结构。用于其他兼容 Agent 前应验证触发、工具权限与脚本环境。
- **安装方式：** Claude Code 可添加 `anthropics/skills` Marketplace；也可按 Agent Skills 目录规范安装对应技能目录。
- **执行验证：** 本卡片仅完成来源审阅，尚未在阿福环境中安装和运行验证。
- **安全要求：** 安装前审查 `SKILL.md`、脚本、依赖、网络访问和写操作权限；高风险操作应先获得用户确认。

## 信息源

- **技能目录：** https://github.com/anthropics/skills/tree/main/skills/frontend-design
- **SKILL.md：** https://github.com/anthropics/skills/blob/main/skills/frontend-design/SKILL.md
- **来源仓库：** https://github.com/anthropics/skills
- **仓库热度：** 约 164k（仓库级 Star，不代表单个 Skill）
- **审阅日期：** 2026-07-23


<!-- CARD 01 END -->


<!-- CARD 02 START -->

---
card_id: "skill-002"
card_type: "skill"
name: "webapp-testing"
display_name: "Web Application Testing"
category: "前端测试"
source_owner: "anthropics"
source_repository: "anthropics/skills"
source_repository_stars_at_review: "约 164k（仓库级 Star，不代表单个 Skill）"
source_url: "https://github.com/anthropics/skills/tree/main/skills/webapp-testing"
source_skill_file: "https://github.com/anthropics/skills/blob/main/skills/webapp-testing/SKILL.md"
license: "以对应技能目录中的 LICENSE.txt 为准"
reviewed_at: "2026-07-23"
review_status: "source_reviewed"
execution_verified: false
risk_level: "medium"
tags:
  - "前端测试"
  - "agent-skill"
  - "anthropics"
  - "webapp-testing"
---

# Web Application Testing

## 核心结论

使用 Playwright 与辅助脚本测试本地 Web 应用，覆盖页面交互验证、UI 行为调试、浏览器日志检查和截图取证，并支持在测试期间管理一个或多个本地服务。

## 适用场景

- 验证按钮、表单、路由和状态变化
- 复现浏览器中的 UI Bug
- 对本地前后端联调流程做自动化检查
- 需要浏览器截图、控制台日志或 DOM 证据

## 触发表达

- 测试这个网页
- 检查按钮能不能用
- 用 Playwright 验证
- 复现这个 UI 问题
- 截取浏览器运行结果

## 主要能力

- 区分静态 HTML 与动态应用并选择检查方式
- 通过 Playwright 执行真实浏览器交互
- 管理本地服务器生命周期及多服务启动
- 先侦察页面状态再确定选择器与动作
- 收集截图、DOM 状态和浏览器日志

## 限制与不适用情况

- 需要可运行的本地项目及 Playwright 环境
- 对第三方验证码、登录挑战和受限网络环境可能无法自动完成
- 测试脚本不等于完整测试策略，仍需明确关键路径和预期结果

## 使用前应确认

- 项目启动命令与端口
- 目标浏览器和测试路径
- 是否允许安装 Playwright 依赖
- 是否涉及真实账号、支付或生产数据

## 阿福推荐策略

当用户说“页面做好了，帮我验证”或遇到难以定位的 UI 问题时推荐。阿福应先整理待验证行为、预期结果和风险边界，再交给该 Skill 执行浏览器验证。

## 兼容性与安装

- **兼容性说明：** 原生面向 Claude；采用 Agent Skills 结构。用于其他兼容 Agent 前应验证触发、工具权限与脚本环境。
- **安装方式：** Claude Code 可添加 `anthropics/skills` Marketplace；也可按 Agent Skills 目录规范安装对应技能目录。
- **执行验证：** 本卡片仅完成来源审阅，尚未在阿福环境中安装和运行验证。
- **安全要求：** 安装前审查 `SKILL.md`、脚本、依赖、网络访问和写操作权限；高风险操作应先获得用户确认。

## 信息源

- **技能目录：** https://github.com/anthropics/skills/tree/main/skills/webapp-testing
- **SKILL.md：** https://github.com/anthropics/skills/blob/main/skills/webapp-testing/SKILL.md
- **来源仓库：** https://github.com/anthropics/skills
- **仓库热度：** 约 164k（仓库级 Star，不代表单个 Skill）
- **审阅日期：** 2026-07-23


<!-- CARD 02 END -->


<!-- CARD 03 START -->

---
card_id: "skill-003"
card_type: "skill"
name: "web-artifacts-builder"
display_name: "Web Artifacts Builder"
category: "复杂 Web 原型"
source_owner: "anthropics"
source_repository: "anthropics/skills"
source_repository_stars_at_review: "约 164k（仓库级 Star，不代表单个 Skill）"
source_url: "https://github.com/anthropics/skills/tree/main/skills/web-artifacts-builder"
source_skill_file: "https://github.com/anthropics/skills/blob/main/skills/web-artifacts-builder/SKILL.md"
license: "以对应技能目录中的 LICENSE.txt 为准"
reviewed_at: "2026-07-23"
review_status: "source_reviewed"
execution_verified: false
risk_level: "medium"
tags:
  - "复杂 Web 原型"
  - "agent-skill"
  - "anthropics"
  - "web-artifacts-builder"
---

# Web Artifacts Builder

## 核心结论

用于构建具有多个组件、状态管理、路由或组件库依赖的复杂 HTML Web Artifact，推荐技术栈包括 React、TypeScript、Vite、Tailwind CSS 与 shadcn/ui，并可将项目打包为单一 HTML。

## 适用场景

- 制作多组件交互原型或演示应用
- 需要状态管理、路由或 shadcn/ui
- 将复杂前端打包成单一 HTML 交付
- 普通单文件 HTML 已无法满足需求

## 触发表达

- 做一个复杂交互原型
- 需要 React 和路由
- 做成单文件 HTML Artifact
- 使用 shadcn/ui
- 生成多页面演示

## 主要能力

- 初始化前端项目骨架
- 使用 React 18、TypeScript、Vite、Tailwind 与 shadcn/ui 开发
- 将项目打包为单个 HTML 文件
- 支持可选的浏览器测试流程
- 提醒避免过度居中、紫色渐变和统一大圆角等常见模板化表现

## 限制与不适用情况

- 不适合非常简单的静态页面或一次性小组件
- 打包为单 HTML 时需关注资源体积和外部依赖
- 生成的原型仍需在目标运行环境中验证

## 使用前应确认

- 是否真的需要路由或复杂状态
- 目标交付是源码还是单 HTML
- 可用依赖和运行环境
- 是否需要离线运行

## 阿福推荐策略

当需求已经超出简单页面，且需要可交互、多组件的前端演示时推荐。阿福先帮助用户控制范围，避免把原型阶段做成完整生产系统。

## 兼容性与安装

- **兼容性说明：** 原生面向 Claude；采用 Agent Skills 结构。用于其他兼容 Agent 前应验证触发、工具权限与脚本环境。
- **安装方式：** Claude Code 可添加 `anthropics/skills` Marketplace；也可按 Agent Skills 目录规范安装对应技能目录。
- **执行验证：** 本卡片仅完成来源审阅，尚未在阿福环境中安装和运行验证。
- **安全要求：** 安装前审查 `SKILL.md`、脚本、依赖、网络访问和写操作权限；高风险操作应先获得用户确认。

## 信息源

- **技能目录：** https://github.com/anthropics/skills/tree/main/skills/web-artifacts-builder
- **SKILL.md：** https://github.com/anthropics/skills/blob/main/skills/web-artifacts-builder/SKILL.md
- **来源仓库：** https://github.com/anthropics/skills
- **仓库热度：** 约 164k（仓库级 Star，不代表单个 Skill）
- **审阅日期：** 2026-07-23


<!-- CARD 03 END -->


<!-- CARD 04 START -->

---
card_id: "skill-004"
card_type: "skill"
name: "mcp-builder"
display_name: "MCP Builder"
category: "Agent 工具集成"
source_owner: "anthropics"
source_repository: "anthropics/skills"
source_repository_stars_at_review: "约 164k（仓库级 Star，不代表单个 Skill）"
source_url: "https://github.com/anthropics/skills/tree/main/skills/mcp-builder"
source_skill_file: "https://github.com/anthropics/skills/blob/main/skills/mcp-builder/SKILL.md"
license: "以对应技能目录中的 LICENSE.txt 为准"
reviewed_at: "2026-07-23"
review_status: "source_reviewed"
execution_verified: false
risk_level: "high"
tags:
  - "Agent 工具集成"
  - "agent-skill"
  - "anthropics"
  - "mcp-builder"
---

# MCP Builder

## 核心结论

指导使用 TypeScript MCP SDK 或 Python FastMCP 构建高质量 MCP Server，使模型能够通过清晰、可发现、结构化的工具调用访问外部 API 或服务。

## 适用场景

- 将现有 API、数据库或 SaaS 接入 Agent
- 设计 MCP 工具名称、输入输出 Schema 和错误信息
- 选择 stdio 或 Streamable HTTP 传输
- 为 MCP Server 建立测试和评估

## 触发表达

- 做一个 MCP Server
- 让 Agent 调用这个 API
- 把外部服务接给 Claude
- 设计 MCP 工具
- 测试 MCP 服务

## 主要能力

- 研究 MCP 规范和目标 API
- 规划工具覆盖范围与工作流工具
- 使用 Zod/Pydantic 定义输入输出结构
- 设计分页、认证、错误处理与工具注解
- 通过 MCP Inspector 构建测试并设计可验证评估题

## 限制与不适用情况

- 需要先理解目标服务的 API、认证与权限边界
- 高层工作流工具与底层完整 API 覆盖之间需要取舍
- 涉及写操作或外部系统变更时必须进行权限和确认设计

## 使用前应确认

- 目标 API 与认证方式
- 只读还是包含写操作
- 本地 stdio 还是远程 HTTP
- 敏感数据、配额、审计和错误恢复要求

## 阿福推荐策略

当用户想让 Agent 连接外部系统时推荐。阿福应先帮助界定要解决的真实任务、工具权限和危险操作，再交给 MCP Builder 设计服务。

## 兼容性与安装

- **兼容性说明：** 原生面向 Claude；采用 Agent Skills 结构。用于其他兼容 Agent 前应验证触发、工具权限与脚本环境。
- **安装方式：** Claude Code 可添加 `anthropics/skills` Marketplace；也可按 Agent Skills 目录规范安装对应技能目录。
- **执行验证：** 本卡片仅完成来源审阅，尚未在阿福环境中安装和运行验证。
- **安全要求：** 安装前审查 `SKILL.md`、脚本、依赖、网络访问和写操作权限；高风险操作应先获得用户确认。

## 信息源

- **技能目录：** https://github.com/anthropics/skills/tree/main/skills/mcp-builder
- **SKILL.md：** https://github.com/anthropics/skills/blob/main/skills/mcp-builder/SKILL.md
- **来源仓库：** https://github.com/anthropics/skills
- **仓库热度：** 约 164k（仓库级 Star，不代表单个 Skill）
- **审阅日期：** 2026-07-23


<!-- CARD 04 END -->


<!-- CARD 05 START -->

---
card_id: "skill-005"
card_type: "skill"
name: "skill-creator"
display_name: "Skill Creator"
category: "Skill 开发"
source_owner: "anthropics"
source_repository: "anthropics/skills"
source_repository_stars_at_review: "约 164k（仓库级 Star，不代表单个 Skill）"
source_url: "https://github.com/anthropics/skills/tree/main/skills/skill-creator"
source_skill_file: "https://github.com/anthropics/skills/blob/main/skills/skill-creator/SKILL.md"
license: "以对应技能目录中的 LICENSE.txt 为准"
reviewed_at: "2026-07-23"
review_status: "source_reviewed"
execution_verified: false
risk_level: "medium"
tags:
  - "Skill 开发"
  - "agent-skill"
  - "anthropics"
  - "skill-creator"
---

# Skill Creator

## 核心结论

用于创建、修改和优化 Agent Skill，并通过测试提示词、定性评审、量化评估、触发准确性与方差分析持续迭代技能质量。

## 适用场景

- 从零创建一个 SKILL.md
- 改进现有 Skill 的说明和工作流
- 验证 Skill 是否正确触发
- 建立测试集与性能基准

## 触发表达

- 帮我写一个 Skill
- 优化这个 SKILL.md
- 测试 Skill 效果
- Skill 为什么不触发
- 给 Skill 做评估

## 主要能力

- 澄清技能目标和预期流程
- 起草或重构 Skill
- 生成测试提示词与量化评估
- 比较有无 Skill 的运行结果
- 根据用户评审和指标迭代
- 优化 description 的触发准确率

## 限制与不适用情况

- 需要可执行的测试环境才能真正衡量效果
- 高分测试集不能替代真实任务中的人工验收
- 技能过度宽泛会导致误触发，过窄会导致漏触发

## 使用前应确认

- Skill 的明确任务边界
- 目标 Agent 与工具权限
- 成功和失败如何判断
- 是否允许执行脚本或批量评测

## 阿福推荐策略

当用户要沉淀可复用工作流或改造 Skill 时推荐。阿福可以先把模糊经验整理为目标、触发条件、步骤、限制和验收标准。

## 兼容性与安装

- **兼容性说明：** 原生面向 Claude；采用 Agent Skills 结构。用于其他兼容 Agent 前应验证触发、工具权限与脚本环境。
- **安装方式：** Claude Code 可添加 `anthropics/skills` Marketplace；也可按 Agent Skills 目录规范安装对应技能目录。
- **执行验证：** 本卡片仅完成来源审阅，尚未在阿福环境中安装和运行验证。
- **安全要求：** 安装前审查 `SKILL.md`、脚本、依赖、网络访问和写操作权限；高风险操作应先获得用户确认。

## 信息源

- **技能目录：** https://github.com/anthropics/skills/tree/main/skills/skill-creator
- **SKILL.md：** https://github.com/anthropics/skills/blob/main/skills/skill-creator/SKILL.md
- **来源仓库：** https://github.com/anthropics/skills
- **仓库热度：** 约 164k（仓库级 Star，不代表单个 Skill）
- **审阅日期：** 2026-07-23


<!-- CARD 05 END -->


<!-- CARD 06 START -->

---
card_id: "skill-006"
card_type: "skill"
name: "claude-api"
display_name: "Claude API Reference"
category: "Claude API 开发"
source_owner: "anthropics"
source_repository: "anthropics/skills"
source_repository_stars_at_review: "约 164k（仓库级 Star，不代表单个 Skill）"
source_url: "https://github.com/anthropics/skills/tree/main/skills/claude-api"
source_skill_file: "https://github.com/anthropics/skills/blob/main/skills/claude-api/SKILL.md"
license: "以对应技能目录中的 LICENSE.txt 为准"
reviewed_at: "2026-07-23"
review_status: "source_reviewed"
execution_verified: false
risk_level: "medium"
tags:
  - "Claude API 开发"
  - "agent-skill"
  - "anthropics"
  - "claude-api"
---

# Claude API Reference

## 核心结论

面向 Claude API 与 Anthropic SDK 的参考技能，覆盖模型标识、参数、流式输出、工具调用、MCP、Agent、缓存、Token 计数和模型迁移，并针对多种语言提供实现参考。

## 适用场景

- 集成 Claude API 或 Anthropic SDK
- 选择模型和参数
- 实现 streaming、tool use、prompt caching
- 处理 Token、模型迁移或 API 调试

## 触发表达

- 接入 Claude API
- Anthropic SDK 怎么用
- Claude 工具调用
- Claude 流式输出
- 模型缓存和 Token

## 主要能力

- 提供多语言 SDK 参考
- 指导消息、流式响应和工具调用
- 处理缓存、Token 计数和迁移
- 帮助区分 Claude 与其他模型提供商的实现
- 要求对时效性信息优先查阅最新参考而非凭记忆回答

## 限制与不适用情况

- 模型、价格、参数和限制可能变化，使用前必须重新核对官方资料
- 不适用于已明确使用 OpenAI、Gemini 等其他提供商的任务
- 密钥、账单和生产权限仍需用户自行安全管理

## 使用前应确认

- 目标语言和 SDK
- 目标模型与区域
- 是否需要工具调用、缓存或流式输出
- 当前使用的 API 版本

## 阿福推荐策略

当用户明确使用 Claude/Anthropic 或尚未决定 LLM 提供商但任务与 Claude API 高度相关时推荐。阿福应避免把过时模型信息写成确定事实。

## 兼容性与安装

- **兼容性说明：** 原生面向 Claude；采用 Agent Skills 结构。用于其他兼容 Agent 前应验证触发、工具权限与脚本环境。
- **安装方式：** Claude Code 可添加 `anthropics/skills` Marketplace；也可按 Agent Skills 目录规范安装对应技能目录。
- **执行验证：** 本卡片仅完成来源审阅，尚未在阿福环境中安装和运行验证。
- **安全要求：** 安装前审查 `SKILL.md`、脚本、依赖、网络访问和写操作权限；高风险操作应先获得用户确认。

## 信息源

- **技能目录：** https://github.com/anthropics/skills/tree/main/skills/claude-api
- **SKILL.md：** https://github.com/anthropics/skills/blob/main/skills/claude-api/SKILL.md
- **来源仓库：** https://github.com/anthropics/skills
- **仓库热度：** 约 164k（仓库级 Star，不代表单个 Skill）
- **审阅日期：** 2026-07-23


<!-- CARD 06 END -->


<!-- CARD 07 START -->

---
card_id: "skill-007"
card_type: "skill"
name: "doc-coauthoring"
display_name: "Doc Co-Authoring"
category: "结构化写作"
source_owner: "anthropics"
source_repository: "anthropics/skills"
source_repository_stars_at_review: "约 164k（仓库级 Star，不代表单个 Skill）"
source_url: "https://github.com/anthropics/skills/tree/main/skills/doc-coauthoring"
source_skill_file: "https://github.com/anthropics/skills/blob/main/skills/doc-coauthoring/SKILL.md"
license: "以对应技能目录中的 LICENSE.txt 为准"
reviewed_at: "2026-07-23"
review_status: "source_reviewed"
execution_verified: false
risk_level: "low"
tags:
  - "结构化写作"
  - "agent-skill"
  - "anthropics"
  - "doc-coauthoring"
---

# Doc Co-Authoring

## 核心结论

以“上下文收集—结构与内容精炼—读者测试”三阶段协作流程，帮助用户共同撰写文档、提案、技术规格、PRD、RFC 和决策文档。

## 适用场景

- 撰写 PRD、RFC、设计文档或提案
- 将零散想法整理成可供他人阅读的结构
- 通过多轮反馈优化文档
- 检查新读者能否独立理解文档

## 触发表达

- 写一份方案
- 起草 PRD
- 写 RFC
- 整理技术设计文档
- 帮我共同完善这份文档

## 主要能力

- 主动收集背景、受众和目标
- 设计文档结构并逐节完善
- 通过迭代减少歧义和遗漏
- 从目标读者角度做阅读测试
- 适合需要上下文迁移的长文档任务

## 限制与不适用情况

- 不是文件格式处理工具；需要生成 DOCX/PDF 时应再配合对应文件 Skill
- 用户若只需要很短的改写，不必使用完整三阶段流程
- 读者测试仍不能代替领域专家审核

## 使用前应确认

- 文档类型、受众和用途
- 已有材料和必须保留的事实
- 篇幅、格式和截止要求
- 谁负责最终审核

## 阿福推荐策略

当用户开始大型文档任务时推荐。阿福可先把目标、受众、已知材料和验收标准整理成任务契约。

## 兼容性与安装

- **兼容性说明：** 原生面向 Claude；采用 Agent Skills 结构。用于其他兼容 Agent 前应验证触发、工具权限与脚本环境。
- **安装方式：** Claude Code 可添加 `anthropics/skills` Marketplace；也可按 Agent Skills 目录规范安装对应技能目录。
- **执行验证：** 本卡片仅完成来源审阅，尚未在阿福环境中安装和运行验证。
- **安全要求：** 安装前审查 `SKILL.md`、脚本、依赖、网络访问和写操作权限；高风险操作应先获得用户确认。

## 信息源

- **技能目录：** https://github.com/anthropics/skills/tree/main/skills/doc-coauthoring
- **SKILL.md：** https://github.com/anthropics/skills/blob/main/skills/doc-coauthoring/SKILL.md
- **来源仓库：** https://github.com/anthropics/skills
- **仓库热度：** 约 164k（仓库级 Star，不代表单个 Skill）
- **审阅日期：** 2026-07-23


<!-- CARD 07 END -->


<!-- CARD 08 START -->

---
card_id: "skill-008"
card_type: "skill"
name: "docx"
display_name: "DOCX"
category: "Word 文档"
source_owner: "anthropics"
source_repository: "anthropics/skills"
source_repository_stars_at_review: "约 164k（仓库级 Star，不代表单个 Skill）"
source_url: "https://github.com/anthropics/skills/tree/main/skills/docx"
source_skill_file: "https://github.com/anthropics/skills/blob/main/skills/docx/SKILL.md"
license: "Proprietary；完整条款见技能目录 LICENSE.txt"
reviewed_at: "2026-07-23"
review_status: "source_reviewed"
execution_verified: false
risk_level: "low"
tags:
  - "Word 文档"
  - "agent-skill"
  - "anthropics"
  - "docx"
---

# DOCX

## 核心结论

用于创建、读取、编辑和重组 DOCX/DOTX 文件，包括专业排版、目录、标题、页码、页眉页脚、图片、查找替换、批注和修订等操作。

## 适用场景

- 创建正式 Word 报告、信函、模板或备忘录
- 编辑现有 DOCX 文件
- 提取或重排 Word 内容
- 处理图片、批注或修订

## 触发表达

- 生成 Word 文档
- 修改这个 docx
- 做一个带目录的报告
- 替换 Word 里的图片
- 处理修订和批注

## 主要能力

- 创建具有专业结构的 DOCX
- 读取和提取 Word 内容
- 通过 XML 方式编辑现有文档
- 处理页眉页脚、页码和目录
- 支持图片替换、查找替换、批注与修订场景

## 限制与不适用情况

- 该技能目录为 source-available/proprietary 条款，不能默认视作开源
- 现有 DOCX 编辑可能需要直接处理 Office XML
- 输出后必须进行渲染检查，避免分页和样式异常

## 使用前应确认

- 纸张、字体、字号、页边距和行距
- 是否有模板或品牌规范
- 是否需要目录、页码和封面
- 是否必须保留修订或批注

## 阿福推荐策略

当最终交付物明确为 Word 文件时推荐。阿福应先确认格式规范和内容结构，再调用 DOCX Skill。

## 兼容性与安装

- **兼容性说明：** 原生面向 Claude；采用 Agent Skills 结构。用于其他兼容 Agent 前应验证触发、工具权限与脚本环境。
- **安装方式：** Claude Code 可添加 `anthropics/skills` Marketplace；也可按 Agent Skills 目录规范安装对应技能目录。
- **执行验证：** 本卡片仅完成来源审阅，尚未在阿福环境中安装和运行验证。
- **安全要求：** 安装前审查 `SKILL.md`、脚本、依赖、网络访问和写操作权限；高风险操作应先获得用户确认。

## 信息源

- **技能目录：** https://github.com/anthropics/skills/tree/main/skills/docx
- **SKILL.md：** https://github.com/anthropics/skills/blob/main/skills/docx/SKILL.md
- **来源仓库：** https://github.com/anthropics/skills
- **仓库热度：** 约 164k（仓库级 Star，不代表单个 Skill）
- **审阅日期：** 2026-07-23


<!-- CARD 08 END -->


<!-- CARD 09 START -->

---
card_id: "skill-009"
card_type: "skill"
name: "pdf"
display_name: "PDF"
category: "PDF 处理"
source_owner: "anthropics"
source_repository: "anthropics/skills"
source_repository_stars_at_review: "约 164k（仓库级 Star，不代表单个 Skill）"
source_url: "https://github.com/anthropics/skills/tree/main/skills/pdf"
source_skill_file: "https://github.com/anthropics/skills/blob/main/skills/pdf/SKILL.md"
license: "Proprietary；完整条款见技能目录 LICENSE.txt"
reviewed_at: "2026-07-23"
review_status: "source_reviewed"
execution_verified: false
risk_level: "medium"
tags:
  - "PDF 处理"
  - "agent-skill"
  - "anthropics"
  - "pdf"
---

# PDF

## 核心结论

覆盖 PDF 的读取、文本和表格提取、合并、拆分、旋转、水印、创建、表单填写、加密解密、图片提取和扫描件 OCR。

## 适用场景

- 读取或分析 PDF
- 创建或合并 PDF
- 填写 PDF 表单
- 对扫描件做 OCR
- 拆页、旋转、加水印或提取图片

## 触发表达

- 处理这个 PDF
- 提取 PDF 表格
- 合并几个 PDF
- 填写 PDF 表单
- 让扫描件可搜索

## 主要能力

- 使用 Python 库和命令行工具处理 PDF
- 执行基本页面与文本操作
- 处理表单和高级参考流程
- 对扫描件执行 OCR
- 创建、加密和解密 PDF

## 限制与不适用情况

- 该技能目录为 source-available/proprietary 条款
- 复杂排版、图表和扫描件可能需要视觉检查
- OCR 结果可能存在识别错误，关键内容需复核

## 使用前应确认

- 输入是否为扫描件
- 是否包含表单、签名或敏感内容
- 允许的页面变更范围
- 是否要求保持原始视觉版式

## 阿福推荐策略

当输入或输出涉及 PDF 时推荐。若是法律、财务等高风险文件，阿福应明确提醒人工复核。

## 兼容性与安装

- **兼容性说明：** 原生面向 Claude；采用 Agent Skills 结构。用于其他兼容 Agent 前应验证触发、工具权限与脚本环境。
- **安装方式：** Claude Code 可添加 `anthropics/skills` Marketplace；也可按 Agent Skills 目录规范安装对应技能目录。
- **执行验证：** 本卡片仅完成来源审阅，尚未在阿福环境中安装和运行验证。
- **安全要求：** 安装前审查 `SKILL.md`、脚本、依赖、网络访问和写操作权限；高风险操作应先获得用户确认。

## 信息源

- **技能目录：** https://github.com/anthropics/skills/tree/main/skills/pdf
- **SKILL.md：** https://github.com/anthropics/skills/blob/main/skills/pdf/SKILL.md
- **来源仓库：** https://github.com/anthropics/skills
- **仓库热度：** 约 164k（仓库级 Star，不代表单个 Skill）
- **审阅日期：** 2026-07-23


<!-- CARD 09 END -->


<!-- CARD 10 START -->

---
card_id: "skill-010"
card_type: "skill"
name: "pptx"
display_name: "PPTX"
category: "演示文稿"
source_owner: "anthropics"
source_repository: "anthropics/skills"
source_repository_stars_at_review: "约 164k（仓库级 Star，不代表单个 Skill）"
source_url: "https://github.com/anthropics/skills/tree/main/skills/pptx"
source_skill_file: "https://github.com/anthropics/skills/blob/main/skills/pptx/SKILL.md"
license: "Proprietary；完整条款见技能目录 LICENSE.txt"
reviewed_at: "2026-07-23"
review_status: "source_reviewed"
execution_verified: false
risk_level: "low"
tags:
  - "演示文稿"
  - "agent-skill"
  - "anthropics"
  - "pptx"
---

# PPTX

## 核心结论

用于创建、读取、编辑和分析 PPTX/POTX 文件，包括演示文稿、路演、模板、布局、讲者备注、评论以及幻灯片合并和拆分。

## 适用场景

- 创建汇报、路演或课程演示
- 修改现有 PPTX
- 从幻灯片提取文字和结构
- 按模板生成或更新页面
- 合并、拆分或检查幻灯片

## 触发表达

- 做一份 PPT
- 修改这个演示文稿
- 读取 pptx
- 按模板做 slides
- 生成路演 deck

## 主要能力

- 使用 PptxGenJS 创建新演示
- 通过 Office XML 编辑现有演示
- 提取每页内容与生成缩略图
- 处理模板、布局和讲者备注
- 支持视觉审查与防止元素溢出

## 限制与不适用情况

- 该技能目录为 source-available/proprietary 条款
- 自动生成的页面必须渲染检查
- 复杂图形和模板兼容性可能需要手工调整

## 使用前应确认

- 页数、受众和讲述时长
- 横纵比例和模板
- 是否需要讲者备注
- 图片、图表和品牌资产来源

## 阿福推荐策略

当用户需要 PPTX 作为最终交付物时推荐。阿福先帮助确定故事线、页面结构、每页目的和视觉约束。

## 兼容性与安装

- **兼容性说明：** 原生面向 Claude；采用 Agent Skills 结构。用于其他兼容 Agent 前应验证触发、工具权限与脚本环境。
- **安装方式：** Claude Code 可添加 `anthropics/skills` Marketplace；也可按 Agent Skills 目录规范安装对应技能目录。
- **执行验证：** 本卡片仅完成来源审阅，尚未在阿福环境中安装和运行验证。
- **安全要求：** 安装前审查 `SKILL.md`、脚本、依赖、网络访问和写操作权限；高风险操作应先获得用户确认。

## 信息源

- **技能目录：** https://github.com/anthropics/skills/tree/main/skills/pptx
- **SKILL.md：** https://github.com/anthropics/skills/blob/main/skills/pptx/SKILL.md
- **来源仓库：** https://github.com/anthropics/skills
- **仓库热度：** 约 164k（仓库级 Star，不代表单个 Skill）
- **审阅日期：** 2026-07-23


<!-- CARD 10 END -->


<!-- CARD 11 START -->

---
card_id: "skill-011"
card_type: "skill"
name: "xlsx"
display_name: "XLSX"
category: "电子表格"
source_owner: "anthropics"
source_repository: "anthropics/skills"
source_repository_stars_at_review: "约 164k（仓库级 Star，不代表单个 Skill）"
source_url: "https://github.com/anthropics/skills/tree/main/skills/xlsx"
source_skill_file: "https://github.com/anthropics/skills/blob/main/skills/xlsx/SKILL.md"
license: "Proprietary；完整条款见技能目录 LICENSE.txt"
reviewed_at: "2026-07-23"
review_status: "source_reviewed"
execution_verified: false
risk_level: "medium"
tags:
  - "电子表格"
  - "agent-skill"
  - "anthropics"
  - "xlsx"
---

# XLSX

## 核心结论

用于读取、创建、编辑、清洗和转换 XLSX、XLSM、XLTX、CSV 与 TSV，支持公式、格式、图表和杂乱表格结构修复，最终交付物应为电子表格文件。

## 适用场景

- 整理或修复 Excel/CSV 数据
- 新增公式、列、格式或图表
- 创建可复用电子表格
- 在表格格式之间转换

## 触发表达

- 处理这个 Excel
- 清洗 CSV
- 给表格加公式
- 生成 xlsx
- 修复错位表头

## 主要能力

- 读取和重构表格数据
- 创建公式、格式和图表
- 处理异常行、错位表头和脏数据
- 在常见表格格式间转换
- 生成可交付的电子表格文件

## 限制与不适用情况

- 该技能目录为 source-available/proprietary 条款
- 宏、外部链接和复杂公式需额外验证
- 若最终交付是报告或数据库管道，不应仅因存在表格数据而触发

## 使用前应确认

- 目标文件格式
- 列含义和数据类型
- 公式与计算规则
- 是否允许修改原始数据
- 是否包含个人或敏感信息

## 阿福推荐策略

当电子表格是主要输入或输出时推荐。阿福应先明确字段、计算规则、输出表结构和数据安全要求。

## 兼容性与安装

- **兼容性说明：** 原生面向 Claude；采用 Agent Skills 结构。用于其他兼容 Agent 前应验证触发、工具权限与脚本环境。
- **安装方式：** Claude Code 可添加 `anthropics/skills` Marketplace；也可按 Agent Skills 目录规范安装对应技能目录。
- **执行验证：** 本卡片仅完成来源审阅，尚未在阿福环境中安装和运行验证。
- **安全要求：** 安装前审查 `SKILL.md`、脚本、依赖、网络访问和写操作权限；高风险操作应先获得用户确认。

## 信息源

- **技能目录：** https://github.com/anthropics/skills/tree/main/skills/xlsx
- **SKILL.md：** https://github.com/anthropics/skills/blob/main/skills/xlsx/SKILL.md
- **来源仓库：** https://github.com/anthropics/skills
- **仓库热度：** 约 164k（仓库级 Star，不代表单个 Skill）
- **审阅日期：** 2026-07-23


<!-- CARD 11 END -->


<!-- CARD 12 START -->

---
card_id: "skill-012"
card_type: "skill"
name: "brand-guidelines"
display_name: "Brand Guidelines"
category: "品牌视觉"
source_owner: "anthropics"
source_repository: "anthropics/skills"
source_repository_stars_at_review: "约 164k（仓库级 Star，不代表单个 Skill）"
source_url: "https://github.com/anthropics/skills/tree/main/skills/brand-guidelines"
source_skill_file: "https://github.com/anthropics/skills/blob/main/skills/brand-guidelines/SKILL.md"
license: "以对应技能目录中的 LICENSE.txt 为准"
reviewed_at: "2026-07-23"
review_status: "source_reviewed"
execution_verified: false
risk_level: "medium"
tags:
  - "品牌视觉"
  - "agent-skill"
  - "anthropics"
  - "brand-guidelines"
---

# Brand Guidelines

## 核心结论

将 Anthropic 官方品牌配色和字体应用到适合的视觉产物中，用于公司品牌、视觉格式和设计标准相关任务。

## 适用场景

- 制作需要符合 Anthropic 品牌的演示、文档或网页
- 检查配色与字体是否符合 Anthropic 风格
- 为现有产物统一 Anthropic 视觉

## 触发表达

- 使用 Anthropic 品牌
- 按 Anthropic 风格设计
- 套用官方配色和字体
- 统一品牌视觉

## 主要能力

- 提供 Anthropic 品牌主色和强调色
- 指定标题与正文字体搭配
- 将品牌规范应用到不同产物
- 保持视觉一致性

## 限制与不适用情况

- 只适用于确实需要 Anthropic 品牌的任务
- 不应把 Anthropic 品牌误用于阿福或其他独立产品
- 品牌资产和商标使用仍需遵守官方条款

## 使用前应确认

- 产物是否真的代表 Anthropic
- 是否存在更高优先级的项目品牌规范
- 使用场景是内部参考还是公开发布

## 阿福推荐策略

仅在用户明确要求 Anthropic 官方视觉时推荐。对阿福项目本身不应默认触发，应优先使用阿福的黑金品牌规范。

## 兼容性与安装

- **兼容性说明：** 原生面向 Claude；采用 Agent Skills 结构。用于其他兼容 Agent 前应验证触发、工具权限与脚本环境。
- **安装方式：** Claude Code 可添加 `anthropics/skills` Marketplace；也可按 Agent Skills 目录规范安装对应技能目录。
- **执行验证：** 本卡片仅完成来源审阅，尚未在阿福环境中安装和运行验证。
- **安全要求：** 安装前审查 `SKILL.md`、脚本、依赖、网络访问和写操作权限；高风险操作应先获得用户确认。

## 信息源

- **技能目录：** https://github.com/anthropics/skills/tree/main/skills/brand-guidelines
- **SKILL.md：** https://github.com/anthropics/skills/blob/main/skills/brand-guidelines/SKILL.md
- **来源仓库：** https://github.com/anthropics/skills
- **仓库热度：** 约 164k（仓库级 Star，不代表单个 Skill）
- **审阅日期：** 2026-07-23


<!-- CARD 12 END -->


<!-- CARD 13 START -->

---
card_id: "skill-013"
card_type: "skill"
name: "theme-factory"
display_name: "Theme Factory"
category: "主题系统"
source_owner: "anthropics"
source_repository: "anthropics/skills"
source_repository_stars_at_review: "约 164k（仓库级 Star，不代表单个 Skill）"
source_url: "https://github.com/anthropics/skills/tree/main/skills/theme-factory"
source_skill_file: "https://github.com/anthropics/skills/blob/main/skills/theme-factory/SKILL.md"
license: "以对应技能目录中的 LICENSE.txt 为准"
reviewed_at: "2026-07-23"
review_status: "source_reviewed"
execution_verified: false
risk_level: "low"
tags:
  - "主题系统"
  - "agent-skill"
  - "anthropics"
  - "theme-factory"
---

# Theme Factory

## 核心结论

为幻灯片、文档、报告和 HTML 页面选择并应用一致的颜色与字体主题，提供预设主题，也支持根据任务临时生成新主题。

## 适用场景

- 同一项目需要统一文档、演示和网页风格
- 用户尚未确定具体视觉主题
- 已有内容需要批量套用字体和颜色系统

## 触发表达

- 给这份内容套个主题
- 统一 PPT 和文档风格
- 选择配色和字体
- 生成一套视觉主题

## 主要能力

- 展示预设主题供用户选择
- 为主题提供完整色板和字体搭配
- 将同一主题应用到多类产物
- 在没有合适预设时生成新主题

## 限制与不适用情况

- 应在用户明确选择后再应用主题
- 主题统一不能替代针对具体页面的信息设计
- 字体在目标环境不可用时需要回退方案

## 使用前应确认

- 应用对象和受众
- 用户希望选择预设还是生成新主题
- 可用字体与品牌禁用项
- 是否需要跨多种文件保持一致

## 阿福推荐策略

当用户需要跨文档、演示或网页维持统一视觉时推荐。阿福先确定品牌约束，再让用户确认主题。

## 兼容性与安装

- **兼容性说明：** 原生面向 Claude；采用 Agent Skills 结构。用于其他兼容 Agent 前应验证触发、工具权限与脚本环境。
- **安装方式：** Claude Code 可添加 `anthropics/skills` Marketplace；也可按 Agent Skills 目录规范安装对应技能目录。
- **执行验证：** 本卡片仅完成来源审阅，尚未在阿福环境中安装和运行验证。
- **安全要求：** 安装前审查 `SKILL.md`、脚本、依赖、网络访问和写操作权限；高风险操作应先获得用户确认。

## 信息源

- **技能目录：** https://github.com/anthropics/skills/tree/main/skills/theme-factory
- **SKILL.md：** https://github.com/anthropics/skills/blob/main/skills/theme-factory/SKILL.md
- **来源仓库：** https://github.com/anthropics/skills
- **仓库热度：** 约 164k（仓库级 Star，不代表单个 Skill）
- **审阅日期：** 2026-07-23


<!-- CARD 13 END -->


<!-- CARD 14 START -->

---
card_id: "skill-014"
card_type: "skill"
name: "react-best-practices"
display_name: "Vercel React Best Practices"
category: "React 性能"
source_owner: "vercel-labs"
source_repository: "vercel-labs/agent-skills"
source_repository_stars_at_review: "约 29.4k（仓库级 Star，不代表单个 Skill）"
source_url: "https://github.com/vercel-labs/agent-skills/tree/main/skills/react-best-practices"
source_skill_file: "https://github.com/vercel-labs/agent-skills/blob/main/skills/react-best-practices/SKILL.md"
license: "MIT"
reviewed_at: "2026-07-23"
review_status: "source_reviewed"
execution_verified: false
risk_level: "medium"
tags:
  - "React 性能"
  - "agent-skill"
  - "vercel-labs"
  - "react-best-practices"
---

# Vercel React Best Practices

## 核心结论

由 Vercel Engineering 维护的 React 与 Next.js 性能优化规则集，按影响程度覆盖异步瀑布、Bundle、服务端、客户端取数、重渲染、渲染和 JavaScript 性能。

## 适用场景

- 编写或审查 React/Next.js 代码
- 优化页面性能和 Bundle
- 重构数据请求与组件渲染
- 检查服务端和客户端性能模式

## 触发表达

- 优化 React 性能
- 检查 Next.js 页面
- 减少重渲染
- 分析 Bundle
- 消除请求瀑布

## 主要能力

- 按严重程度识别性能问题
- 优化异步依赖与并行请求
- 减少 Bundle 和无效导入
- 改善服务端与客户端数据获取
- 处理重渲染、渲染和 JS 微优化

## 限制与不适用情况

- 规则不应机械应用，需结合实际性能证据
- 部分建议与具体 React/Next.js 版本有关
- 优化前应保留测试和基准，避免功能回归

## 使用前应确认

- React/Next.js 版本
- 当前性能问题与测量结果
- 允许修改的组件范围
- 是否已有测试和性能预算

## 阿福推荐策略

当用户进行 React/Next.js 开发、审查或性能优化时优先推荐。阿福应先确认是功能问题还是性能问题，避免过早微优化。

## 兼容性与安装

- **兼容性说明：** 采用 Agent Skills 开放格式，可用于 Claude Code、Codex、Cursor 等兼容 Agent；实际能力取决于目标 Agent 的工具与权限。
- **安装方式：** `npx skills add vercel-labs/agent-skills --skill react-best-practices`
- **执行验证：** 本卡片仅完成来源审阅，尚未在阿福环境中安装和运行验证。
- **安全要求：** 安装前审查 `SKILL.md`、脚本、依赖、网络访问和写操作权限；高风险操作应先获得用户确认。

## 信息源

- **技能目录：** https://github.com/vercel-labs/agent-skills/tree/main/skills/react-best-practices
- **SKILL.md：** https://github.com/vercel-labs/agent-skills/blob/main/skills/react-best-practices/SKILL.md
- **来源仓库：** https://github.com/vercel-labs/agent-skills
- **仓库热度：** 约 29.4k（仓库级 Star，不代表单个 Skill）
- **审阅日期：** 2026-07-23


<!-- CARD 14 END -->


<!-- CARD 15 START -->

---
card_id: "skill-015"
card_type: "skill"
name: "web-design-guidelines"
display_name: "Web Design Guidelines"
category: "UI/UX 审查"
source_owner: "vercel-labs"
source_repository: "vercel-labs/agent-skills"
source_repository_stars_at_review: "约 29.4k（仓库级 Star，不代表单个 Skill）"
source_url: "https://github.com/vercel-labs/agent-skills/tree/main/skills/web-design-guidelines"
source_skill_file: "https://github.com/vercel-labs/agent-skills/blob/main/skills/web-design-guidelines/SKILL.md"
license: "MIT"
reviewed_at: "2026-07-23"
review_status: "source_reviewed"
execution_verified: false
risk_level: "medium"
tags:
  - "UI/UX 审查"
  - "agent-skill"
  - "vercel-labs"
  - "web-design-guidelines"
---

# Web Design Guidelines

## 核心结论

使用 Web Interface Guidelines 对 UI 代码进行审查，覆盖无障碍、焦点、表单、动画、排版、图片、性能、导航状态、深色模式、触控和国际化等规则。

## 适用场景

- 审查已有 UI 的可用性与无障碍
- 上线前做界面质量检查
- 检查表单、键盘操作、暗色主题和移动端
- 找出设计实现中的常见遗漏

## 触发表达

- 审查我的 UI
- 检查可访问性
- 做 UX Audit
- 检查网页最佳实践
- 上线前检查界面

## 主要能力

- 检查语义 HTML、ARIA 和键盘行为
- 审查焦点状态、表单反馈和错误处理
- 检查动画与 reduced-motion
- 发现图片、性能和布局抖动问题
- 检查 URL 状态、深色模式、触控和国际化

## 限制与不适用情况

- 代码规则审查不能代替真实用户测试
- 若技能动态读取远程指南，应固定或审核来源版本
- 规则数量较多，应只输出与当前页面相关的高优先级问题

## 使用前应确认

- 要审查的页面或代码范围
- 目标设备与浏览器
- 是否有 WCAG 或组织级标准
- 允许自动修改还是仅输出报告

## 阿福推荐策略

当页面基本完成、准备验收或用户提出“哪里不对”时推荐。阿福应要求输出按严重度排序，而不是一次倾倒全部规则。

## 兼容性与安装

- **兼容性说明：** 采用 Agent Skills 开放格式，可用于 Claude Code、Codex、Cursor 等兼容 Agent；实际能力取决于目标 Agent 的工具与权限。
- **安装方式：** `npx skills add vercel-labs/agent-skills --skill web-design-guidelines`
- **执行验证：** 本卡片仅完成来源审阅，尚未在阿福环境中安装和运行验证。
- **安全要求：** 安装前审查 `SKILL.md`、脚本、依赖、网络访问和写操作权限；高风险操作应先获得用户确认。

## 信息源

- **技能目录：** https://github.com/vercel-labs/agent-skills/tree/main/skills/web-design-guidelines
- **SKILL.md：** https://github.com/vercel-labs/agent-skills/blob/main/skills/web-design-guidelines/SKILL.md
- **来源仓库：** https://github.com/vercel-labs/agent-skills
- **仓库热度：** 约 29.4k（仓库级 Star，不代表单个 Skill）
- **审阅日期：** 2026-07-23


<!-- CARD 15 END -->


<!-- CARD 16 START -->

---
card_id: "skill-016"
card_type: "skill"
name: "composition-patterns"
display_name: "React Composition Patterns"
category: "React 架构"
source_owner: "vercel-labs"
source_repository: "vercel-labs/agent-skills"
source_repository_stars_at_review: "约 29.4k（仓库级 Star，不代表单个 Skill）"
source_url: "https://github.com/vercel-labs/agent-skills/tree/main/skills/composition-patterns"
source_skill_file: "https://github.com/vercel-labs/agent-skills/blob/main/skills/composition-patterns/SKILL.md"
license: "MIT"
reviewed_at: "2026-07-23"
review_status: "source_reviewed"
execution_verified: false
risk_level: "medium"
tags:
  - "React 架构"
  - "agent-skill"
  - "vercel-labs"
  - "composition-patterns"
---

# React Composition Patterns

## 核心结论

提供可扩展的 React 组合模式，重点避免布尔属性膨胀，通过复合组件、状态提升和内部组合设计更灵活的组件 API。

## 适用场景

- 组件拥有大量 boolean props
- 构建可复用组件库
- 重构组件 API
- 减少 prop drilling 和组件耦合

## 触发表达

- 重构这个 React 组件
- boolean props 太多
- 做复合组件
- 设计可复用组件 API
- 减少 prop drilling

## 主要能力

- 识别布尔属性爆炸
- 提取 compound components
- 通过状态提升改善边界
- 使用内部组合提高扩展性
- 指导组件 API 设计

## 限制与不适用情况

- 小型一次性组件不一定需要复杂组合模式
- 过度抽象会增加学习成本
- 重构必须配合行为测试避免破坏调用方

## 使用前应确认

- 组件的真实复用场景
- 现有调用方数量
- API 兼容要求
- 是否允许破坏性重构

## 阿福推荐策略

当用户遇到组件扩展困难或属性不断增加时推荐。阿福先帮助区分真实复用需求与过度设计。

## 兼容性与安装

- **兼容性说明：** 采用 Agent Skills 开放格式，可用于 Claude Code、Codex、Cursor 等兼容 Agent；实际能力取决于目标 Agent 的工具与权限。
- **安装方式：** `npx skills add vercel-labs/agent-skills --skill composition-patterns`
- **执行验证：** 本卡片仅完成来源审阅，尚未在阿福环境中安装和运行验证。
- **安全要求：** 安装前审查 `SKILL.md`、脚本、依赖、网络访问和写操作权限；高风险操作应先获得用户确认。

## 信息源

- **技能目录：** https://github.com/vercel-labs/agent-skills/tree/main/skills/composition-patterns
- **SKILL.md：** https://github.com/vercel-labs/agent-skills/blob/main/skills/composition-patterns/SKILL.md
- **来源仓库：** https://github.com/vercel-labs/agent-skills
- **仓库热度：** 约 29.4k（仓库级 Star，不代表单个 Skill）
- **审阅日期：** 2026-07-23


<!-- CARD 16 END -->


<!-- CARD 17 START -->

---
card_id: "skill-017"
card_type: "skill"
name: "react-native-guidelines"
display_name: "React Native Guidelines"
category: "移动端开发"
source_owner: "vercel-labs"
source_repository: "vercel-labs/agent-skills"
source_repository_stars_at_review: "约 29.4k（仓库级 Star，不代表单个 Skill）"
source_url: "https://github.com/vercel-labs/agent-skills/tree/main/skills/react-native-guidelines"
source_skill_file: "https://github.com/vercel-labs/agent-skills/blob/main/skills/react-native-guidelines/SKILL.md"
license: "MIT"
reviewed_at: "2026-07-23"
review_status: "source_reviewed"
execution_verified: false
risk_level: "medium"
tags:
  - "移动端开发"
  - "agent-skill"
  - "vercel-labs"
  - "react-native-guidelines"
---

# React Native Guidelines

## 核心结论

面向 React Native 与 Expo 的性能、布局、动画、图片、状态管理、架构和平台差异最佳实践。

## 适用场景

- 开发 React Native 或 Expo 应用
- 优化列表、动画和图片性能
- 处理安全区域与键盘
- 设计 iOS/Android 平台差异

## 触发表达

- 做 React Native 应用
- Expo 性能优化
- 移动端动画卡顿
- 处理安全区和键盘
- 优化 RN 列表

## 主要能力

- 指导高性能列表和 memoization
- 处理 Flex、Safe Area 与键盘布局
- 使用 Reanimated 与手势模式
- 优化图片缓存和懒加载
- 提供状态、架构和平台差异建议

## 限制与不适用情况

- 建议可能依赖 React Native、Expo 与库版本
- 涉及原生模块时仍需平台开发环境
- 移动端性能应在真实设备验证

## 使用前应确认

- Expo 还是 Bare React Native
- 目标 iOS/Android 版本
- 使用的导航、动画和状态库
- 是否有真实设备测试条件

## 阿福推荐策略

当用户明确做移动应用而非网页时推荐。阿福应先确认平台、运行方式和是否需要原生能力。

## 兼容性与安装

- **兼容性说明：** 采用 Agent Skills 开放格式，可用于 Claude Code、Codex、Cursor 等兼容 Agent；实际能力取决于目标 Agent 的工具与权限。
- **安装方式：** `npx skills add vercel-labs/agent-skills --skill react-native-guidelines`
- **执行验证：** 本卡片仅完成来源审阅，尚未在阿福环境中安装和运行验证。
- **安全要求：** 安装前审查 `SKILL.md`、脚本、依赖、网络访问和写操作权限；高风险操作应先获得用户确认。

## 信息源

- **技能目录：** https://github.com/vercel-labs/agent-skills/tree/main/skills/react-native-guidelines
- **SKILL.md：** https://github.com/vercel-labs/agent-skills/blob/main/skills/react-native-guidelines/SKILL.md
- **来源仓库：** https://github.com/vercel-labs/agent-skills
- **仓库热度：** 约 29.4k（仓库级 Star，不代表单个 Skill）
- **审阅日期：** 2026-07-23


<!-- CARD 17 END -->


<!-- CARD 18 START -->

---
card_id: "skill-018"
card_type: "skill"
name: "react-view-transitions"
display_name: "React View Transitions"
category: "前端动画"
source_owner: "vercel-labs"
source_repository: "vercel-labs/agent-skills"
source_repository_stars_at_review: "约 29.4k（仓库级 Star，不代表单个 Skill）"
source_url: "https://github.com/vercel-labs/agent-skills/tree/main/skills/react-view-transitions"
source_skill_file: "https://github.com/vercel-labs/agent-skills/blob/main/skills/react-view-transitions/SKILL.md"
license: "MIT"
reviewed_at: "2026-07-23"
review_status: "source_reviewed"
execution_verified: false
risk_level: "low"
tags:
  - "前端动画"
  - "agent-skill"
  - "vercel-labs"
  - "react-view-transitions"
---

# React View Transitions

## 核心结论

指导在 React 和 Next.js 中使用 View Transition API 实现页面、组件和共享元素过渡，并处理方向性导航、列表重排、Suspense 和 reduced-motion。

## 适用场景

- 增加路由或页面过渡
- 实现列表到详情的共享元素动画
- 制作前进/后退方向性动画
- 改善组件进出和列表重排体验

## 触发表达

- 加页面切换动画
- 做共享元素过渡
- React ViewTransition
- Next.js 路由动画
- 列表重排动画

## 主要能力

- 使用 ViewTransition 组件
- 定义 transition type
- 结合 CSS 伪元素和 Web Animations API
- 集成 Next.js App Router
- 提供 fade、slide、scale、flip 等动画方案
- 尊重 reduced-motion

## 限制与不适用情况

- 浏览器与 React/Next.js 版本支持需确认
- 动画不能掩盖性能和信息结构问题
- 过多动画会降低效率和可访问性

## 使用前应确认

- 目标浏览器和框架版本
- 动画是必要反馈还是装饰
- 方向性与共享元素规则
- 减少动画模式下的替代体验

## 阿福推荐策略

当用户已经确定界面结构并明确需要动画时推荐，不应在需求尚未清楚时提前触发。

## 兼容性与安装

- **兼容性说明：** 采用 Agent Skills 开放格式，可用于 Claude Code、Codex、Cursor 等兼容 Agent；实际能力取决于目标 Agent 的工具与权限。
- **安装方式：** `npx skills add vercel-labs/agent-skills --skill react-view-transitions`
- **执行验证：** 本卡片仅完成来源审阅，尚未在阿福环境中安装和运行验证。
- **安全要求：** 安装前审查 `SKILL.md`、脚本、依赖、网络访问和写操作权限；高风险操作应先获得用户确认。

## 信息源

- **技能目录：** https://github.com/vercel-labs/agent-skills/tree/main/skills/react-view-transitions
- **SKILL.md：** https://github.com/vercel-labs/agent-skills/blob/main/skills/react-view-transitions/SKILL.md
- **来源仓库：** https://github.com/vercel-labs/agent-skills
- **仓库热度：** 约 29.4k（仓库级 Star，不代表单个 Skill）
- **审阅日期：** 2026-07-23


<!-- CARD 18 END -->


<!-- CARD 19 START -->

---
card_id: "skill-019"
card_type: "skill"
name: "writing-guidelines"
display_name: "Vercel Writing Guidelines"
category: "技术写作审查"
source_owner: "vercel-labs"
source_repository: "vercel-labs/agent-skills"
source_repository_stars_at_review: "约 29.4k（仓库级 Star，不代表单个 Skill）"
source_url: "https://github.com/vercel-labs/agent-skills/tree/main/skills/writing-guidelines"
source_skill_file: "https://github.com/vercel-labs/agent-skills/blob/main/skills/writing-guidelines/SKILL.md"
license: "MIT"
reviewed_at: "2026-07-23"
review_status: "source_reviewed"
execution_verified: false
risk_level: "low"
tags:
  - "技术写作审查"
  - "agent-skill"
  - "vercel-labs"
  - "writing-guidelines"
---

# Vercel Writing Guidelines

## 核心结论

按照 Vercel 写作手册审查文档和产品文字，覆盖内容规划、语气、标题结构、列表、代码示例、占位符、数字单位、排版与 AI 工作流责任。

## 适用场景

- 审查技术文档与产品说明
- 统一文档语气和结构
- 检查教程、How-to、参考文档和故障排查文章
- 优化代码示例与标题

## 触发表达

- 审查我的文档
- 统一写作风格
- 检查技术文档语气
- 优化这篇教程
- 按写作手册修改

## 主要能力

- 区分不同内容类型和语气
- 检查主动语态与面向用户表达
- 优化标题、列表和结构
- 规范代码示例、数字、单位和占位符
- 提醒作者对 AI 产出负责并进行审查

## 限制与不适用情况

- 它体现 Vercel 的写作规范，不一定适合所有组织
- 组织或比赛已有格式要求时应以其为准
- 不应为了规则一致性牺牲事实准确性

## 使用前应确认

- 文档受众和用途
- 采用 Vercel 规范还是仅借鉴
- 组织已有术语和格式
- 是否允许重写结构

## 阿福推荐策略

当用户需要技术文档质量审查时推荐；若是阿福参赛材料，应先遵守主办方格式和用户的中文表达偏好。

## 兼容性与安装

- **兼容性说明：** 采用 Agent Skills 开放格式，可用于 Claude Code、Codex、Cursor 等兼容 Agent；实际能力取决于目标 Agent 的工具与权限。
- **安装方式：** `npx skills add vercel-labs/agent-skills --skill writing-guidelines`
- **执行验证：** 本卡片仅完成来源审阅，尚未在阿福环境中安装和运行验证。
- **安全要求：** 安装前审查 `SKILL.md`、脚本、依赖、网络访问和写操作权限；高风险操作应先获得用户确认。

## 信息源

- **技能目录：** https://github.com/vercel-labs/agent-skills/tree/main/skills/writing-guidelines
- **SKILL.md：** https://github.com/vercel-labs/agent-skills/blob/main/skills/writing-guidelines/SKILL.md
- **来源仓库：** https://github.com/vercel-labs/agent-skills
- **仓库热度：** 约 29.4k（仓库级 Star，不代表单个 Skill）
- **审阅日期：** 2026-07-23


<!-- CARD 19 END -->


<!-- CARD 20 START -->

---
card_id: "skill-020"
card_type: "skill"
name: "vercel-optimize"
display_name: "Vercel Optimize"
category: "部署性能与成本"
source_owner: "vercel-labs"
source_repository: "vercel-labs/agent-skills"
source_repository_stars_at_review: "约 29.4k（仓库级 Star，不代表单个 Skill）"
source_url: "https://github.com/vercel-labs/agent-skills/tree/main/skills/vercel-optimize"
source_skill_file: "https://github.com/vercel-labs/agent-skills/blob/main/skills/vercel-optimize/SKILL.md"
license: "MIT"
reviewed_at: "2026-07-23"
review_status: "source_reviewed"
execution_verified: false
risk_level: "high"
tags:
  - "部署性能与成本"
  - "agent-skill"
  - "vercel-labs"
  - "vercel-optimize"
---

# Vercel Optimize

## 核心结论

基于 Vercel 项目指标审计成本、性能、可靠性、缓存、函数使用和计费机会，再针对指标指向的路由与文件进行深入分析并输出排序后的改进报告。

## 适用场景

- 优化已部署的 Vercel 项目
- 降低函数、构建或带宽成本
- 排查慢路由和高开销请求
- 检查缓存、ISR、中间件与图片配置

## 触发表达

- 优化 Vercel 项目
- 降低 Vercel 成本
- 分析慢路由
- 检查函数使用
- 做部署性能报告

## 主要能力

- 先收集项目指标再定位代码
- 审计成本、性能和可靠性
- 发现缓存、ISR、中间件、图片和构建时间问题
- 输出按收益和影响排序的报告

## 限制与不适用情况

- 需要 Vercel 项目访问权限和可用指标
- 指标可能包含业务与访问信息，应控制日志和输出
- 建议修改前应确认环境、回滚与验证计划

## 使用前应确认

- 项目与环境范围
- 只读权限是否足够
- 成本和性能目标
- 是否允许访问生产指标
- 变更后的验证与回滚方式

## 阿福推荐策略

当用户已经部署到 Vercel 并明确要优化成本或性能时推荐。阿福应先确认只读审计还是允许修改，避免未经确认触碰生产配置。

## 兼容性与安装

- **兼容性说明：** 采用 Agent Skills 开放格式，可用于 Claude Code、Codex、Cursor 等兼容 Agent；实际能力取决于目标 Agent 的工具与权限。
- **安装方式：** `npx skills add vercel-labs/agent-skills --skill vercel-optimize`
- **执行验证：** 本卡片仅完成来源审阅，尚未在阿福环境中安装和运行验证。
- **安全要求：** 安装前审查 `SKILL.md`、脚本、依赖、网络访问和写操作权限；高风险操作应先获得用户确认。

## 信息源

- **技能目录：** https://github.com/vercel-labs/agent-skills/tree/main/skills/vercel-optimize
- **SKILL.md：** https://github.com/vercel-labs/agent-skills/blob/main/skills/vercel-optimize/SKILL.md
- **来源仓库：** https://github.com/vercel-labs/agent-skills
- **仓库热度：** 约 29.4k（仓库级 Star，不代表单个 Skill）
- **审阅日期：** 2026-07-23


<!-- CARD 20 END -->
