"""
PGVector 向量存储 — 替代 ChromaDB。

与 ChatLab 共用 pgvector/pgvector:pg16 容器。
Embedding 生成: DashScope text-embedding-v3 (1024维)，与 ChatLab 一致。

用法:
    store = PGVectorStore(connection_string)
    await store.ensure_tables()
    ids = await store.add("domain_knowledge", documents, embeddings, metadatas)
    results = await store.search("domain_knowledge", query_embedding, top_k=5)
"""

import hashlib
import json
import logging
from datetime import datetime
from typing import Optional

import psycopg2
import psycopg2.extras
from psycopg2 import sql

logger = logging.getLogger(__name__)


class PGVectorStore:
    """PostgreSQL + PGVector 向量存储。

    每个 collection 对应一张表:
      - domain_knowledge  : RAG 领域知识
      - session_memory    : L2 会话摘要
      - user_profile      : L3 用户画像（单文档）

    表结构:
      CREATE TABLE {collection} (
          id         TEXT PRIMARY KEY,
          document   TEXT NOT NULL,
          embedding  vector(1024) NOT NULL,
          metadata   JSONB DEFAULT '{}',
          created_at TIMESTAMPTZ DEFAULT NOW()
      );
      CREATE INDEX ON {collection} USING ivfflat (embedding vector_cosine_ops);
    """

    # 所有 collection 定义
    COLLECTIONS = {
        "domain_knowledge": {
            "description": "领域知识库 — RAG 检索",
            "embedding_dim": 1024,
            "index_lists": 100,  # IVFFlat 索引的 lists 参数
        },
        "session_memory": {
            "description": "跨会话记忆 — LLM 摘要向量化",
            "embedding_dim": 1024,
            "index_lists": 50,
        },
        "user_profile": {
            "description": "用户画像 — 长期偏好学习（单文档）",
            "embedding_dim": 1024,
            "index_lists": 10,
        },
    }

    def __init__(self, connection_string: str):
        """
        Args:
            connection_string: PostgreSQL 连接串
               格式: host=localhost port=5432 dbname=makeitsmooth user=postgres password=xxx
        """
        self.conn_string = connection_string
        self._conn: Optional[psycopg2.extensions.connection] = None

    # ============================================================
    # 连接管理
    # ============================================================

    @property
    def conn(self):
        """懒加载 PostgreSQL 连接。"""
        if self._conn is None or self._conn.closed:
            self._conn = psycopg2.connect(self.conn_string)
            self._conn.autocommit = False
            psycopg2.extras.register_vector(self._conn)  # 注册 pgvector 适配器
        return self._conn

    def close(self):
        if self._conn and not self._conn.closed:
            self._conn.close()

    # ============================================================
    # 表管理
    # ============================================================

    async def ensure_tables(self) -> dict:
        """确保所有 collection 表 + pgvector 扩展 + 索引存在。返回状态。"""
        results = {}
        try:
            cur = self.conn.cursor()

            # 启用 pgvector 扩展
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
            self.conn.commit()

            for coll_name, coll_config in self.COLLECTIONS.items():
                dim = coll_config["embedding_dim"]
                exists = await self._table_exists(coll_name)

                if not exists:
                    cur.execute(sql.SQL("""
                        CREATE TABLE {} (
                            id          TEXT PRIMARY KEY,
                            document    TEXT NOT NULL,
                            embedding   vector({}) NOT NULL,
                            metadata    JSONB DEFAULT '{}'::jsonb,
                            created_at  TIMESTAMPTZ DEFAULT NOW()
                        )
                    """).format(sql.Identifier(coll_name), sql.Literal(dim)))
                    self.conn.commit()
                    results[coll_name] = "created"
                    logger.info(f"[PGVector] 创建表: {coll_name}")
                else:
                    results[coll_name] = "exists"

                # 确保索引存在
                idx_name = f"idx_{coll_name}_embedding"
                cur.execute(sql.SQL("""
                    SELECT 1 FROM pg_indexes WHERE indexname = %s
                """), (idx_name,))
                if cur.fetchone() is None:
                    lists = coll_config["index_lists"]
                    cur.execute(sql.SQL("""
                        CREATE INDEX {} ON {}
                        USING ivfflat (embedding vector_cosine_ops)
                        WITH (lists = {})
                    """).format(
                        sql.Identifier(idx_name),
                        sql.Identifier(coll_name),
                        sql.Literal(lists),
                    ))
                    self.conn.commit()
                    logger.info(f"[PGVector] 创建索引: {idx_name}")

            cur.close()
        except Exception as e:
            self.conn.rollback()
            logger.error(f"[PGVector] 表初始化失败: {e}")
            raise
        return results

    async def _table_exists(self, table_name: str) -> bool:
        cur = self.conn.cursor()
        cur.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = %s
            )
        """, (table_name,))
        result = cur.fetchone()[0]
        cur.close()
        return result

    # ============================================================
    # CRUD
    # ============================================================

    async def add(
        self,
        collection: str,
        documents: list[str],
        embeddings: list[list[float]],
        metadatas: Optional[list[dict]] = None,
        ids: Optional[list[str]] = None,
    ) -> list[str]:
        """向 collection 添加文档 + embedding。

        Args:
            collection: 表名 (domain_knowledge / session_memory / user_profile)
            documents: 文档文本列表
            embeddings: 对应的 1024 维向量列表
            metadatas: 元数据列表（可选）
            ids: 文档 ID 列表（可选，自动生成）

        Returns:
            写入的 ID 列表
        """
        if metadatas is None:
            metadatas = [{}] * len(documents)
        if ids is None:
            ids = [self._make_id(doc, i) for i, doc in enumerate(documents)]

        cur = self.conn.cursor()
        inserted = []

        try:
            for id_, doc, emb, meta in zip(ids, documents, embeddings, metadatas):
                cur.execute(
                    sql.SQL("""
                        INSERT INTO {} (id, document, embedding, metadata)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (id) DO UPDATE SET
                            document = EXCLUDED.document,
                            embedding = EXCLUDED.embedding,
                            metadata = EXCLUDED.metadata,
                            created_at = NOW()
                    """).format(sql.Identifier(collection)),
                    (id_, doc, emb, json.dumps(meta, ensure_ascii=False)),
                )
                inserted.append(id_)

            self.conn.commit()
        except Exception as e:
            self.conn.rollback()
            logger.error(f"[PGVector] 写入失败 ({collection}): {e}")
            raise
        finally:
            cur.close()

        return inserted

    async def search(
        self,
        collection: str,
        query_embedding: list[float],
        top_k: int = 5,
        filter_meta: Optional[dict] = None,
    ) -> list[dict]:
        """向量相似度检索。

        Args:
            collection: 表名
            query_embedding: 查询向量 (1024维)
            top_k: 返回数量
            filter_meta: 可选的 metadata 过滤条件

        Returns:
            [{id, document, metadata, score}, ...]
        """
        cur = self.conn.cursor()

        try:
            if filter_meta:
                # 带 metadata 过滤
                filter_json = json.dumps(filter_meta)
                cur.execute(
                    sql.SQL("""
                        SELECT id, document, metadata,
                               1 - (embedding <=> %s::vector) AS score
                        FROM {}
                        WHERE metadata @> %s::jsonb
                        ORDER BY embedding <=> %s::vector
                        LIMIT %s
                    """).format(sql.Identifier(collection)),
                    (query_embedding, filter_json, query_embedding, top_k),
                )
            else:
                cur.execute(
                    sql.SQL("""
                        SELECT id, document, metadata,
                               1 - (embedding <=> %s::vector) AS score
                        FROM {}
                        ORDER BY embedding <=> %s::vector
                        LIMIT %s
                    """).format(sql.Identifier(collection)),
                    (query_embedding, query_embedding, top_k),
                )

            rows = cur.fetchall()
            results = []
            for row in rows:
                results.append({
                    "id": row[0],
                    "document": row[1],
                    "metadata": row[2] if isinstance(row[2], dict) else json.loads(row[2] or "{}"),
                    "score": float(row[3]),
                })
            return results

        except Exception as e:
            self.conn.rollback()
            logger.error(f"[PGVector] 检索失败 ({collection}): {e}")
            return []
        finally:
            cur.close()

    async def get_by_id(self, collection: str, doc_id: str) -> Optional[dict]:
        """按 ID 获取单个文档。"""
        cur = self.conn.cursor()
        cur.execute(
            sql.SQL("SELECT id, document, metadata FROM {} WHERE id = %s").format(
                sql.Identifier(collection)
            ),
            (doc_id,),
        )
        row = cur.fetchone()
        cur.close()
        if row:
            return {
                "id": row[0],
                "document": row[1],
                "metadata": row[2] if isinstance(row[2], dict) else json.loads(row[2] or "{}"),
            }
        return None

    async def delete(self, collection: str, ids: list[str]) -> int:
        """按 ID 删除文档。返回删除数量。"""
        cur = self.conn.cursor()
        cur.execute(
            sql.SQL("DELETE FROM {} WHERE id = ANY(%s)").format(
                sql.Identifier(collection)
            ),
            (ids,),
        )
        deleted = cur.rowcount
        self.conn.commit()
        cur.close()
        return deleted

    async def count(self, collection: str) -> int:
        """返回 collection 中的文档数。"""
        cur = self.conn.cursor()
        cur.execute(
            sql.SQL("SELECT COUNT(*) FROM {}").format(sql.Identifier(collection))
        )
        count = cur.fetchone()[0]
        cur.close()
        return count

    async def clear(self, collection: str):
        """清空 collection 的所有数据。"""
        cur = self.conn.cursor()
        cur.execute(
            sql.SQL("DELETE FROM {}").format(sql.Identifier(collection))
        )
        self.conn.commit()
        cur.close()

    # ============================================================
    # 工具方法
    # ============================================================

    def _make_id(self, text: str, index: int = 0) -> str:
        raw = f"{text[:100]}:{index}:{datetime.now().timestamp()}"
        return hashlib.md5(raw.encode()).hexdigest()[:16]


def build_connection_string(config) -> str:
    """从 Config 对象构建 PostgreSQL 连接字符串。

    优先使用环境变量，与 ChatLab 共用 PG 实例:
      - DB_HOST: PostgreSQL 地址 (默认 localhost)
      - DB_PORT: 端口 (默认 5432)
      - PGSQLPASSWORD: 密码
      - DB_NAME: 数据库名 (默认 makeitsmooth, ChatLab 用 chatdemopg)
    """
    import os

    host = getattr(config, "pg_host", None) or os.getenv("DB_HOST", "localhost")
    port = getattr(config, "pg_port", None) or os.getenv("DB_PORT", "5432")
    dbname = getattr(config, "pg_database", None) or os.getenv("DB_NAME", "makeitsmooth")
    user = getattr(config, "pg_user", None) or os.getenv("DB_USER", "postgres")
    password = getattr(config, "pg_password", None) or os.getenv("PGSQLPASSWORD", "")

    if not password:
        raise ValueError(
            "PGSQLPASSWORD 环境变量未设置。"
            "请设置 PostgreSQL 密码（与 ChatLab 共用同一个 PG 实例）。\n"
            "本地开发: 在 .env 中设置 PGSQLPASSWORD\n"
            "Docker 部署: docker-compose 自动注入"
        )

    return (
        f"host={host} port={port} dbname={dbname} "
        f"user={user} password={password} "
        f"connect_timeout=10"
    )
