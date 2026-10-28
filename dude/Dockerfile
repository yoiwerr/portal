FROM python:3.12-slim

WORKDIR /app

RUN sed -i 's/deb.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list.d/debian.sources \
    && apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
    -i https://mirrors.aliyun.com/pypi/simple/ \
    --trusted-host mirrors.aliyun.com uv

COPY pyproject.toml uv.lock ./

ENV UV_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/ \
    UV_INSECURE_HOST=mirrors.aliyun.com \
    PATH="/app/.venv/bin:$PATH"

RUN uv sync --frozen --no-dev --no-cache

COPY . .
