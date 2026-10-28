# Portal 本地开发与 dude 联调

更新：2026-10-22。本轮推进 08：让已实现的 dude 规划流程可通过统一入口登录和试用。业务界面、数据库名称和生产 nginx 未改。

## 启动与配置

Linux/WSL 使用 Python 3.12、uv、Go 1.22+。PostgreSQL 实例和项目数据库应事先可用；`make dev` 不创建业务库。Journal 需先按自身说明执行 Alembic 迁移。启动 Go 会按其既有行为执行迁移和首次管理员初始化，因此数据库地址必须指向你打算用于开发的库。

从 Portal 根目录执行：

```bash
cd /home/yoiwerr/portal
make dev
```

保留原 `.env`，手动核对以下配置，不把真实值提交 Git：

| 配置 | 规则 |
| --- | --- |
| DB_HOST / DB_PORT / DB_NAME / DB_USER | Python 与 Go 共用；未设置时回退 PG_HOST / PG_PORT / PG_DATABASE / PG_USER |
| PGSQLPASSWORD | 必填；Go URL 自动编码特殊字符，无需拼接另一个连接串 |
| JWT_SECRET | 必填且至少 32 字符；两个服务共用 |
| ADMIN_INIT_PASSWORD | 必填，首次创建 admin 使用；不重置已有账号，拒绝旧 admin123 默认 |
| JOURNAL_DATABASE_URL | 可选，开发时使用 postgresql+psycopg 连接串，显式值优先 |
| JOURNAL_DB_PASSWORD | 无显式 Journal URL 时必填；使用同一实例的 journal/journal_user |
| LLM_PROVIDER 和对应聊天模型配置 | 按 dude README；本轮不需要嵌入凭证 |

`.env.example` 是示例，不要直接把 replace-with 值当凭证。Go 的 DATABASE_URL 由上表派生；启动器不沿用可能指向另一库的通用 DATABASE_URL。`make dev` 通过 uv 读取根 `.env`，直接 `python3 run_dev.py` 则只读已导出的进程环境。Go 直跑的历史默认配置未在本轮修改，统一启动器会事先拦截缺失值。

启动顺序为 Go 构建 → 三后端 → 健康检查 → Portal。Go 二进制放在临时目录，结束清理；Python 使用 `uv run --frozen`，Go 构建使用 `-mod=readonly`，不顺便更新依赖。任何构建/启动失败都会清理本次子进程并非零退出，不打印整体成功。运行中后端退出也会停止整组服务并报错。

## 访问入口

| 内容 | 地址 |
| --- | --- |
| Portal | http://localhost:8080/ |
| dude 聊天 | http://localhost:8080/dude/ |
| 登录/注册 | http://localhost:8080/dude/auth/ |
| 管理后台 | http://localhost:8080/dude/admin/ |
| Journal | http://localhost:8080/journal/ |
| Python 就绪检查 | http://127.0.0.1:8001/api/health |
| Go 健康检查 | http://127.0.0.1:8083/api/v1/health |
| Journal 健康检查 | http://127.0.0.1:8002/journal/health |

全部服务只监听回环地址，适用于本机开发。现有管理员使用原密码；新测试库的初始管理员为 admin，密码来自你自己的环境配置。普通用户通过注册创建。不要拿临时测试账号尝试生产登录。

统一代理先识别 Go 登录/管理及静态资源、新旧认证 API，再处理 Python 对话路径；保留查询参数、Authorization、Cookie 和请求体。PUT/DELETE/PATCH 等使用同一分流。上游错误码、WWW-Authenticate、多个 Set-Cookie、字符编码会透传；重定向不在服务端自动跟随，内部 Location 回写到 Portal 路径。

SSE 逐块立即转发，首条进度不用等整轮结束；并发 HTTP 服务让其他页面不被聊天请求阻塞。静态目录、.html 回退和目录 index 都做 resolve 边界校验，拒绝编码路径穿越与符号链接越界。

## 停止与端口冲突

原终端 Ctrl+C，或者另一个终端：

```bash
cd /home/yoiwerr/portal
make stop
```

`.portal-dev.lock` 只记录启动器 PID、进程开始时间和目录；进程锁保证同一项目只启动一组。stop 核对记录、命令和工作目录，使用 pidfd 给该实例发停止信号。启动器回收自己创建的进程组并等待后代退出，覆盖 uv 包装的 Python 进程。不会执行 fuser -k，也不会因端口占用杀掉其他人的服务。无记录或进程已退出时无需操作，身份不匹配会报错。

该机制需要现代 Linux 的 /proc、flock、pidfd（Linux 5.3+），适用于 WSL2。锁文件已加入 `.gitignore`，保持原地、不复制；Go 临时构建也无需手动放到服务器。

端口占用会列出 ss 可见的进程；无 ss 时至少检查能否绑定并报告端口。先确认旧进程归属再停止。WSL 的 localhost 转发有时在 Linux 进程退出后仍接受短暂握手，实际端口释放以 Linux 监听状态或重新 bind 为准。

## 验证与限制

不接业务数据库的回归：

```bash
python3 -m unittest discover -s tests -p 'test_*.py' -v
git diff --check
```

包含原有 ChatLab 下线路由，以及 Go 路径、写方法、Cookie/错误/重定向、SSE 首事件、并发访问、静态越界、配置编码、端口占用、身份核对与受控进程回收。

本轮验证结果：21 项开发入口回归和 91 项规划离线回归通过，Python 语法与 git diff --check 通过。真实栈验证使用独立临时 PostgreSQL、临时 alfred_dev_test/journal_test 库与随机凭证，运行 Journal 迁移后启动实际 Go/Python/Journal，登录、令牌刷新、管理员目录、普通用户拒绝访问管理接口、Python 验证 Go JWT，以及 make stop 后四个端口重新绑定均通过。测试不调用在线模型，不触碰已有业务库或管理员；结束已停止临时服务。

本轮不等于浏览器视觉验收或真实模型质量验收，也未验证服务器 Docker/nginx。当前 Python 部分资源的用户归属隔离仍未完善，不能把统一登录正常视为全站多用户安全完成。Go 健康接口仍是进程就绪信号，不是持续数据库探活；启动器运行中监控进程退出，不提供服务重启或生产守护。
