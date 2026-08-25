"""
Token 用量记录服务 — LLM 调用完成后异步写入 admin_token_usage 表。

Go Admin 读这张表做统计展示，Python 只负责写。
"""

import asyncio
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

# Build connection string from env (same as session_store / vector_store)
def _build_conn_string() -> str:
    host = os.getenv("DB_HOST", os.getenv("PG_HOST", "localhost"))
    port = os.getenv("DB_PORT", os.getenv("PG_PORT", "5432"))
    dbname = os.getenv("DB_NAME", os.getenv("PG_DATABASE", "alfred"))
    user = os.getenv("DB_USER", os.getenv("PG_USER", "postgres"))
    password = os.getenv("PGSQLPASSWORD", os.getenv("PG_PASSWORD", ""))
    return f"host={host} port={port} dbname={dbname} user={user} password={password}"


CONN_STRING = _build_conn_string()


def _record_sync(
    user_id: str,
    provider: str,
    model_name: str,
    input_tokens: int,
    output_tokens: int,
    duration_ms: float = 0.0,
    success: bool = True,
    error_message: str = "",
    session_id: Optional[str] = None,
):
    """同步写入（在 asyncio.to_thread 中执行）。"""
    import psycopg

    try:
        conn = psycopg.connect(CONN_STRING)
        conn.execute(
            """
            INSERT INTO admin_token_usage
                (user_id, session_id, provider, model_name,
                 input_tokens, output_tokens, total_tokens,
                 duration_ms, success, error_message)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                user_id,
                session_id or "",
                provider,
                model_name,
                input_tokens,
                output_tokens,
                input_tokens + output_tokens,
                duration_ms,
                success,
                error_message,
            ),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.warning(f"[Usage] 写入 token_usage 失败（不影响对话）: {e}")


def record_usage(
    user_id: str = "",
    provider: str = "",
    model_name: str = "",
    input_tokens: int = 0,
    output_tokens: int = 0,
    duration_ms: float = 0.0,
    success: bool = True,
    error_message: str = "",
    session_id: Optional[str] = None,
):
    """异步记录 Token 用量。不阻塞调用方。"""
    if not user_id:
        return  # 没有用户上下文时不记录（本地开发未登录场景）

    try:
        asyncio.create_task(
            asyncio.to_thread(
                _record_sync,
                user_id,
                provider,
                model_name,
                input_tokens,
                output_tokens,
                duration_ms,
                success,
                error_message,
                session_id,
            )
        )
    except Exception as e:
        logger.warning(f"[Usage] 创建异步任务失败: {e}")
