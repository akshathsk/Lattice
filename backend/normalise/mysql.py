"""
MySQL normaliser — same structure as the Postgres normaliser, using pymysql.
"""

from __future__ import annotations

import logging
from typing import Any

import pymysql
import pymysql.cursors

from .base    import BaseNormaliser
from .chunker import chunk_record, DEFAULT_CHUNK_SIZE, DEFAULT_OVERLAP
from .models  import NormalisedChunk

logger = logging.getLogger(__name__)

_SKIP_TABLES = {"information_schema", "performance_schema", "mysql", "sys"}


class MySQLNormaliser(BaseNormaliser):
    SOURCE = "mysql"

    def __init__(
        self,
        *,
        host:       str = "localhost",
        port:       int = 3306,
        dbname:     str,
        user:       str,
        password:   str,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        overlap:    int = DEFAULT_OVERLAP,
    ) -> None:
        self._conn_kwargs = dict(
            host=host, port=int(port), database=dbname,
            user=user, password=password,
            cursorclass=pymysql.cursors.DictCursor,
            connect_timeout=10,
        )
        self._dbname     = dbname
        self._chunk_size = chunk_size
        self._overlap    = overlap

    def health_check(self) -> bool:
        try:
            conn = pymysql.connect(**self._conn_kwargs)
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
            conn.close()
            return True
        except Exception:
            return False

    def normalise(self, *, query=None, tables=None, collections=None) -> list[NormalisedChunk]:
        chunks: list[NormalisedChunk] = []
        conn = pymysql.connect(**self._conn_kwargs)
        try:
            if query:
                chunks.extend(self._run_query(conn, query, collection="custom_query"))
            else:
                target = tables or self._discover_tables(conn)
                for table in target:
                    logger.info("mysql: reading table %s", table)
                    chunks.extend(self._run_query(conn, f"SELECT * FROM `{table}`", collection=table))
        finally:
            conn.close()
        logger.info("mysql: produced %d chunks", len(chunks))
        return chunks

    def _discover_tables(self, conn) -> list[str]:
        with conn.cursor() as cur:
            cur.execute("SHOW TABLES")
            return [list(row.values())[0] for row in cur.fetchall()]

    def _run_query(self, conn, sql: str, collection: str) -> list[NormalisedChunk]:
        chunks: list[NormalisedChunk] = []
        with conn.cursor() as cur:
            cur.execute(sql)
            rows = cur.fetchall()
            for row_idx, row in enumerate(rows):
                record_id = str(row.get("id") or row.get("_id") or row_idx)
                text = self._row_to_text(collection, row)
                for idx, part in chunk_record(text, record_id=record_id, collection=collection,
                                              size=self._chunk_size, overlap=self._overlap):
                    chunks.append(NormalisedChunk(
                        source=self.SOURCE, database=self._dbname, collection=collection,
                        record_id=record_id, chunk_index=idx, text=part,
                        metadata=_safe_metadata(row),
                    ))
        return chunks

    def _row_to_text(self, table: str, row: dict[str, Any]) -> str:
        record_id = row.get("id") or row.get("_id") or ""
        lines = [f"[Table: {table} | ID: {record_id}]"]
        for col, val in row.items():
            if val is None:
                continue
            val_str = self._coerce_str(val)
            if val_str:
                lines.append(f"{col}: {val_str}")
        return "\n".join(lines)


def _safe_metadata(row: dict[str, Any]) -> dict[str, Any]:
    import datetime
    safe: dict[str, Any] = {}
    for k, v in row.items():
        if isinstance(v, (datetime.date, datetime.datetime)):
            safe[k] = v.isoformat()
        elif isinstance(v, (str, int, float, bool)) or v is None:
            safe[k] = v
        else:
            safe[k] = str(v)
    return safe
