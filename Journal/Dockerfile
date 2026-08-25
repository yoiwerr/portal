FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN pip install --no-cache-dir uv && uv sync --frozen --no-dev
COPY app.py create_user.py alembic.ini ./
COPY migrations ./migrations
COPY static ./static
RUN useradd --create-home --uid 10001 journal && chown -R journal:journal /app
USER journal
EXPOSE 8000
CMD ["sh","-c","uv run alembic upgrade head && uv run uvicorn app:app --host 0.0.0.0 --port 8000"]
