FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml uv.lock ./
ARG PYTHON_PACKAGE_INDEX=https://mirrors.aliyun.com/pypi/simple/
RUN pip install --no-cache-dir --index-url "$PYTHON_PACKAGE_INDEX" uv==0.11.26 \
    && UV_DEFAULT_INDEX="$PYTHON_PACKAGE_INDEX" uv sync --frozen --no-dev
COPY app.py create_user.py alembic.ini ./
COPY migrations ./migrations
COPY static ./static
RUN useradd --create-home --uid 10001 journal && chown -R journal:journal /app
USER journal
EXPOSE 8000
CMD ["sh","-c","uv run --no-dev alembic upgrade head && uv run --no-dev uvicorn app:app --host 0.0.0.0 --port 8000"]
