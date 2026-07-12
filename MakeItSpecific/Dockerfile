FROM python:3.12-slim

WORKDIR /app

# 国内镜像加速：Debian apt 源
RUN sed -i 's/deb.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list.d/debian.sources \
    && apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# uv 安装依赖
RUN pip install --no-cache-dir -i https://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com uv

RUN uv pip install --system --no-cache-dir \
    -i https://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com \
    fastapi uvicorn sse-starlette \
    psycopg-binary httpx pydantic python-dotenv \
    dashscope langchain langchain-community langchain-openai langgraph \
    pytest pytest-asyncio

COPY . .

RUN mkdir -p /app/data && chmod 777 /app/data

EXPOSE 8000

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
