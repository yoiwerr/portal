# syntax=docker/dockerfile:1.7
FROM python:3.12-slim

WORKDIR /app

# Psycopg 3 uses libpq at runtime; build-essential/libpq-dev are not required.
RUN sed -i 's/deb.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list.d/debian.sources \
    && apt-get update && apt-get install -y --no-install-recommends libpq5 curl \
    && rm -rf /var/lib/apt/lists/*

ARG PYTHON_PACKAGE_INDEX=https://mirrors.aliyun.com/pypi/simple/
RUN pip install --no-cache-dir --index-url "$PYTHON_PACKAGE_INDEX" uv==0.11.26

COPY pyproject.toml uv.lock ./

ENV UV_DEFAULT_INDEX=${PYTHON_PACKAGE_INDEX} \
    UV_CONCURRENT_DOWNLOADS=2 \
    UV_CONCURRENT_BUILDS=1 \
    UV_CONCURRENT_INSTALLS=1 \
    PATH="/app/.venv/bin:$PATH"

# Export exact locked versions/hashes, then fetch wheels from the configured mirror.
# uv sync --frozen alone follows files.pythonhosted.org URLs embedded in uv.lock.
# Wheel-only install fails explicitly rather than unexpectedly compiling on the server.
RUN --mount=type=cache,target=/root/.cache/uv,sharing=locked \
    uv export --frozen --no-dev --no-emit-project --output-file /tmp/requirements.txt \
    && uv venv /app/.venv \
    && uv pip sync --python /app/.venv/bin/python --require-hashes --only-binary :all: \
       --index-url "$PYTHON_PACKAGE_INDEX" --link-mode=copy /tmp/requirements.txt \
    && rm /tmp/requirements.txt

COPY . .
