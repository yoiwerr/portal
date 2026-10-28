# dude 浅色对话界面

本轮对齐「面向新手的新项目方案助手」定位，保留原生 HTML/CSS/JavaScript、现有账号服务与规划 API。没有引入 React、在线字体、前端构建依赖或新的环境变量。

## 页面与交互

- 首页先呈现项目输入框；三个示例只填入草稿，由用户修改并发送。
- 开始对话后，输入框固定在底部。方案摘要首次有内容时在桌面自动展开，手机只出现入口，主动打开后作为可关闭的抽屉。
- 对话目录按需打开；支持按轮次跳转。摘要支持确认、修改和错误反馈，失败不会显示成功。
- 登录、注册与聊天统一浅色、深灰正文、蓝色操作。输入区和正文使用 16px 字号；中文输入法选词时 Enter 不发送。
- 方案中的标题、列表、表格、引用和安全链接可读；模型输出作为文本转义，不执行 HTML。
- 每条回复可以复制或下载 Markdown。这里下载的是该条回复，尚未增加独立的方案版本库或最终方案导出接口。
- 首页移除旧项目记忆、旧项目继续和未实现的附件入口；后端旧接口不在本轮删除。这份界面说明原先未涵盖管理后台；随后工作区已新增用户与用量视图，现状见 [后台 README](../dude-admin/README.md)。
- 开始新想法前提醒保存当前内容；刷新页面仍不会自动恢复当前对话，这项原有能力限制尚未改变。

## 接口兼容

认证仍使用 `/dude/api/v1/auth/*`。聊天及摘要操作在 Portal 下使用 `/dude/api/*`，直接运行 Python 首页时使用 `/api/*`，避免使用已停用的 Portal 根级 `/api` 路径（当前生产返回 410）。

SSE 读取支持分块、CRLF、心跳、错误及正常结束；缺少回复或请求失败会清理等待状态并保留输入，以便重试。测试使用确定性模拟响应，不替代真实数据库及模型联调。

## 参考

- [Lovable Plan mode](https://docs.lovable.dev/features/plan-mode)：对话与方案分开阅读。
- [shadcn/ui Sidebar](https://ui.shadcn.com/blocks/sidebar)：折叠侧栏、浅色分区与操作层级。
- [Lovable Chatbot UI Guide](https://lovable.dev/guides/how-to-build-a-chatbot-ui)：输入、示例与状态反馈。

借鉴交互原则与布局，自行实现页面，没有复制第三方品牌素材或付费组件。使用 `frontend-design` 技能的 Swiss 视觉方向：白色与中性灰背景、无衬线字体、细分隔线、克制的蓝色强调。

## 验证与上线

从 Portal 根目录运行：

```bash
node --test dude/dude-admin/tests/auth.test.cjs
node --check dude/static/js/chat.js
node --check dude/dude-admin/static/js/auth.js
git diff --check
```

浏览器检查登录/注册切换、错误状态、示例草稿、发送与回复、目录跳转、摘要编辑确认、复制/下载、390px 手机布局与抽屉关闭。回归测试覆盖原认证/刷新场景，以及聊天路径、SSE 分块、失败恢复、中文输入法和不可信 Markdown。

代码提交并同步服务器后，从 Portal 根目录更新两个应用容器：

```bash
git pull --ff-only origin master
docker compose build dude-admin dude-api
docker compose up -d --no-deps --force-recreate --wait --wait-timeout 120 dude-admin dude-api
```

这次未修改 nginx、数据库、迁移或 `.env`。页面资源引用带版本参数，更新容器后刷新浏览器即可；若旧 HTML 仍被缓存，使用 Ctrl+F5。
