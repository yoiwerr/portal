"""
PostgreSQL 任务契约持久化。

与 SessionStore 共用同一个 PostgreSQL 实例。
提供契约的创建、读取、更新、版本历史查询。

表: task_contracts — 契约 JSONB + 元数据
"""

import json
import uuid
from datetime import datetime, timezone
from typing import Optional

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

import logging
logger = logging.getLogger(__name__)


class ContractStore:
    """任务契约的 PostgreSQL 存储。"""

    def __init__(self, conn_string: str):
        """
        Args:
            conn_string: PostgreSQL 连接串 (与 SessionStore / PGVectorStore 共用)
        """
        self.conn_string = conn_string
        self._conn: Optional[psycopg.Connection] = None
        self._init_db()

    # ============================================================
    # 连接
    # ============================================================

    @property
    def conn(self):
        if self._conn is None or self._conn.closed:
            self._conn = psycopg.connect(self.conn_string, row_factory=dict_row)
        return self._conn

    def close(self):
        if self._conn and not self._conn.closed:
            self._conn.close()

    # ============================================================
    # 建表
    # ============================================================

    def _init_db(self):
        """创建 task_contracts 表（如不存在）。"""
        cur = self.conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS task_contracts (
                row_id          SERIAL PRIMARY KEY,
                contract_id     TEXT NOT NULL,
                session_id      TEXT NOT NULL,
                version         INTEGER NOT NULL DEFAULT 1,
                contract        JSONB NOT NULL DEFAULT '{}'::jsonb,
                status          TEXT DEFAULT 'draft',
                created_at      TIMESTAMPTZ DEFAULT NOW(),
                confirmed_at    TIMESTAMPTZ,
                UNIQUE(contract_id, version)
            );

            CREATE INDEX IF NOT EXISTS idx_contracts_session
                ON task_contracts(session_id, version DESC);

            CREATE INDEX IF NOT EXISTS idx_contracts_status
                ON task_contracts(status);

            CREATE INDEX IF NOT EXISTS idx_contracts_cid
                ON task_contracts(contract_id);
        """)
        self.conn.commit()
        cur.close()
        logger.info("[ContractStore] 表初始化完成")

    # ============================================================
    # CRUD
    # ============================================================

    def create(self, session_id: str, contract: dict) -> str:
        """
        创建新契约，返回 contract_id。

        Args:
            session_id: 关联会话 ID
            contract: TaskContract 完整 JSON

        Returns:
            contract_id (用于后续 update/confirm 操作)
        """
        contract_id = contract.get("contract_id") or f"tc_{uuid.uuid4().hex[:12]}"
        version = contract.get("version", 1)
        status = contract.get("status", "draft")

        # 确保 contract dict 中有 contract_id
        if "contract_id" not in contract:
            contract["contract_id"] = contract_id

        cur = self.conn.cursor()
        cur.execute(
            """INSERT INTO task_contracts (contract_id, session_id, version, contract, status, created_at)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            (
                contract_id,
                session_id,
                version,
                json.dumps(contract, ensure_ascii=False, default=str),
                status,
                datetime.now(timezone.utc),
            ),
        )
        self.conn.commit()
        cur.close()
        logger.info(f"[ContractStore] 创建契约: {contract_id} v{version} (session={session_id})")
        return contract_id

    def get_latest(self, session_id: str) -> Optional[dict]:
        """
        获取某个会话的最新契约。

        Returns:
            dict: {contract_id, session_id, version, contract, status, created_at, confirmed_at}
            或 None
        """
        cur = self.conn.cursor()
        cur.execute(
            """SELECT contract_id, session_id, version, contract, status, created_at, confirmed_at
               FROM task_contracts
               WHERE session_id = %s
               ORDER BY version DESC
               LIMIT 1""",
            (session_id,),
        )
        row = cur.fetchone()
        cur.close()
        if row:
            result = dict(row)
            if isinstance(result.get("contract"), str):
                result["contract"] = json.loads(result["contract"])
            return result
        return None

    def update(self, contract_id: str, contract: dict, increment_version: bool = True):
        """
        更新已有契约。支持版本历史。

        Args:
            contract_id: 契约 ID（同一会话的不变标识符）
            contract: 更新后的完整契约 JSON
            increment_version: 是否创建新版本（INSERT 新行，保留历史）
        """
        cur = self.conn.cursor()

        if increment_version:
            cur.execute(
                "SELECT version, session_id FROM task_contracts WHERE contract_id = %s ORDER BY version DESC LIMIT 1",
                (contract_id,),
            )
            row = cur.fetchone()
            new_version = (row["version"] + 1) if row else 1
            session_id = row["session_id"] if row else ""
            contract["version"] = new_version
            contract["updated_at"] = datetime.now(timezone.utc).isoformat()

            cur.execute(
                """INSERT INTO task_contracts (contract_id, session_id, version, contract, status, created_at)
                   VALUES (%s, %s, %s, %s, %s, NOW())""",
                (
                    contract_id,
                    session_id,
                    new_version,
                    json.dumps(contract, ensure_ascii=False, default=str),
                    contract.get("status", "draft"),
                ),
            )
        else:
            contract["updated_at"] = datetime.now(timezone.utc).isoformat()
            cur.execute(
                """UPDATE task_contracts
                   SET contract = %s, status = %s
                   WHERE contract_id = %s AND version = (SELECT MAX(version) FROM task_contracts tc2 WHERE tc2.contract_id = task_contracts.contract_id)""",
                (
                    json.dumps(contract, ensure_ascii=False, default=str),
                    contract.get("status", "draft"),
                    contract_id,
                ),
            )

        self.conn.commit()
        cur.close()
        logger.info(f"[ContractStore] 更新契约: {contract_id} v{contract.get('version')}")

    def confirm(self, contract_id: str, contract: dict) -> dict:
        """
        用户确认契约。设置 confirmed_by_user=True, status='confirmed'。

        Returns:
            更新后的契约 JSON
        """
        contract["confirmed_by_user"] = True
        contract["status"] = "confirmed"
        contract["updated_at"] = datetime.now(timezone.utc).isoformat()

        cur = self.conn.cursor()
        cur.execute(
            """UPDATE task_contracts
               SET contract = %s, status = 'confirmed', confirmed_at = NOW()
               WHERE contract_id = %s
                 AND version = (
                   SELECT MAX(version) FROM task_contracts tc2
                   WHERE tc2.contract_id = %s
                 )""",
            (
                json.dumps(contract, ensure_ascii=False, default=str),
                contract_id,
                contract_id,
            ),
        )
        self.conn.commit()
        cur.close()
        logger.info(f"[ContractStore] 用户确认契约: {contract_id}")
        return contract

    def get_history(self, session_id: str) -> list[dict]:
        """
        获取某个会话的契约版本历史，最新的在前。

        Returns:
            [{contract_id, session_id, version, contract, status, created_at}, ...]
        """
        cur = self.conn.cursor()
        cur.execute(
            """SELECT contract_id, session_id, version, contract, status, created_at, confirmed_at
               FROM task_contracts
               WHERE session_id = %s
               ORDER BY version DESC""",
            (session_id,),
        )
        rows = cur.fetchall()
        cur.close()
        results = []
        for row in rows:
            r = dict(row)
            if isinstance(r.get("contract"), str):
                r["contract"] = json.loads(r["contract"])
            results.append(r)
        return results
