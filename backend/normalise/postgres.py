"""
PostgreSQL normaliser.

Reads structured rows from a PostgreSQL database and converts each row into
one or more NormalisedChunk objects.

Row → text conversion
---------------------
Each row is rendered as a labelled key-value block, e.g.:

    [Table: contracts | ID: 3]
    title: SaaS Subscription — IBM Watson
    type: SaaS
    status: active
    effective_date: 2023-06-01
    governing_law: New York, USA
    total_value: 84000.00
    notes: Auto-renews unless 60-day notice

This format is intentionally human-readable so that the embedding model and
downstream LLM see natural prose-like text, not raw CSV.

Long text fields (e.g. clause content) are chunked with overlap; short
structured fields are concatenated before chunking.

Usage
-----
    from normalise.postgres import PostgresNormaliser

    n = PostgresNormaliser(host="localhost", port=5432,
                           dbname="contracts", user="lattice", password="…")

    # Read everything
    chunks = n.normalise()

    # Specific tables only
    chunks = n.normalise(tables=["contracts", "clauses"])

    # Custom query (single dataset)
    chunks = n.normalise(query="SELECT * FROM contracts WHERE status = 'active'")
"""

from __future__ import annotations

import logging
from typing import Any

import psycopg2
import psycopg2.extras

from .base    import BaseNormaliser
from .chunker import chunk_record, DEFAULT_CHUNK_SIZE, DEFAULT_OVERLAP
from .models  import NormalisedChunk

logger = logging.getLogger(__name__)

# Postgres system/internal tables we never want to read.
_SKIP_TABLES = {"spatial_ref_sys", "geography_columns", "geometry_columns"}


class PostgresNormaliser(BaseNormaliser):
    """Normalise rows from a PostgreSQL database into NormalisedChunk objects."""

    SOURCE = "postgres"

    def __init__(
        self,
        *,
        host:       str = "localhost",
        port:       int = 5432,
        dbname:     str,
        user:       str,
        password:   str,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        overlap:    int = DEFAULT_OVERLAP,
    ) -> None:
        self._conn_kwargs = dict(
            host=host, port=port, dbname=dbname, user=user, password=password
        )
        self._dbname     = dbname
        self._chunk_size = chunk_size
        self._overlap    = overlap

    # ── public API ────────────────────────────────────────────────────────────

    def health_check(self) -> bool:
        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
            return True
        except Exception:
            return False

    def normalise(
        self,
        *,
        query:       str | None       = None,
        tables:      list[str] | None = None,
        collections: list[str] | None = None,  # ignored for SQL
    ) -> list[NormalisedChunk]:
        """
        Parameters
        ----------
        query  : Raw SELECT string.  When provided, *tables* is ignored.
                 The result set is treated as a single virtual table named
                 ``"custom_query"``.
        tables : List of table names to read.  When omitted, every user table
                 in the public schema is read.
        """
        chunks: list[NormalisedChunk] = []

        with self._connect() as conn:
            if query:
                chunks.extend(self._run_query(conn, query, collection="custom_query"))
            else:
                target_tables = tables or self._discover_tables(conn)
                for table in target_tables:
                    logger.info("postgres: reading table %s", table)
                    chunks.extend(
                        self._run_query(
                            conn,
                            f'SELECT * FROM "{table}"',  # noqa: S608
                            collection=table,
                        )
                    )

        logger.info("postgres: produced %d chunks total", len(chunks))
        return chunks

    # ── internal ──────────────────────────────────────────────────────────────

    def _connect(self):
        return psycopg2.connect(**self._conn_kwargs)

    def _discover_tables(self, conn) -> list[str]:
        """Return all user tables in the public schema, sorted."""
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT table_name
                FROM   information_schema.tables
                WHERE  table_schema = 'public'
                  AND  table_type   = 'BASE TABLE'
                ORDER BY table_name
                """
            )
            return [
                row[0]
                for row in cur.fetchall()
                if row[0] not in _SKIP_TABLES
            ]

    def _primary_key_column(self, conn, table: str) -> str | None:
        """Return the first primary-key column name, or None."""
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT kcu.column_name
                FROM   information_schema.table_constraints  tc
                JOIN   information_schema.key_column_usage   kcu
                       ON  tc.constraint_name = kcu.constraint_name
                       AND tc.table_schema    = kcu.table_schema
                WHERE  tc.constraint_type = 'PRIMARY KEY'
                  AND  tc.table_name      = %s
                  AND  tc.table_schema    = 'public'
                ORDER BY kcu.ordinal_position
                LIMIT 1
                """,
                (table,),
            )
            row = cur.fetchone()
            return row[0] if row else None

    def _run_query(
        self,
        conn,
        sql:        str,
        collection: str,
    ) -> list[NormalisedChunk]:
        """Execute *sql*, convert each row to chunk(s)."""
        chunks: list[NormalisedChunk] = []

        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql)
            columns = [desc.name for desc in cur.description]

            for row_idx, row in enumerate(cur.fetchall()):
                row_dict = dict(row)

                # Prefer an 'id' column; fall back to row position.
                record_id = str(
                    row_dict.get("id")
                    or row_dict.get("_id")
                    or row_idx
                )

                text = self._row_to_text(collection, row_dict, columns)

                for idx, part in chunk_record(
                    text,
                    record_id=record_id,
                    collection=collection,
                    size=self._chunk_size,
                    overlap=self._overlap,
                ):
                    chunks.append(
                        NormalisedChunk(
                            source      = self.SOURCE,
                            database    = self._dbname,
                            collection  = collection,
                            record_id   = record_id,
                            chunk_index = idx,
                            text        = part,
                            metadata    = self._safe_metadata(row_dict),
                        )
                    )

        return chunks

    # ── text assembly ─────────────────────────────────────────────────────────

    def _row_to_text(
        self,
        table:   str,
        row:     dict[str, Any],
        columns: list[str],
    ) -> str:
        """
        Convert a database row into a human-readable text block.

        Format::

            [Table: contracts | ID: 3]
            title: SaaS Subscription — IBM Watson
            type: SaaS
            …
        """
        record_id = row.get("id") or row.get("_id") or ""
        header    = f"[Table: {table} | ID: {record_id}]"

        lines = [header]
        for col in columns:
            val = row.get(col)
            if val is None:
                continue
            val_str = self._coerce_str(val)
            if val_str:
                lines.append(f"{col}: {val_str}")

        return "\n".join(lines)

    @staticmethod
    def _safe_metadata(row: dict[str, Any]) -> dict[str, Any]:
        """Return a JSON-serialisable copy of the row (dates → ISO strings)."""
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
