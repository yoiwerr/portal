FROM python:3.12-slim

WORKDIR /app

# 国内镜像加速：Debian apt 源 + curl (healthcheck)
RUN sed -i 's/deb.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list.d/debian.sources \
    && apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

# 用 uv 替代 pip（更快、更可靠的依赖解析）
RUN pip install --no-cache-dir -i https://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com uv

# 先复制依赖声明，利用 Docker 层缓存
COPY pyproject.toml ./

# 安装 Python 依赖
RUN uv pip install --system --no-cache-dir \
    -i https://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com \
    fastapi 'uvicorn[standard]' sse-starlette httpx pydantic python-dotenv \
    dashscope langchain langchain-community langchain-openai langgraph \
    psycopg pgvector aiohttp numpy python-multipart

COPY . .
