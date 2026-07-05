"""
Elasticsearch normaliser — reads documents from one or more indices.

Supports basic auth (user + password) or API-key auth (pass the key as password
with no user).  Uses the scroll/scan helper to page through large indices.
"""

from __future__ import annotations

import logging
from typing import Any

from .base    import BaseNormaliser
from .chunker import chunk_record, DEFAULT_CHUNK_SIZE, DEFAULT_OVERLAP
from .models  import NormalisedChunk

logger = logging.getLogger(__name__)

_SKIP_PREFIXES = (".", "kibana", "logstash", "metrics-", "traces-", "logs-")


class ElasticsearchNormaliser(BaseNormaliser):
    SOURCE = "elasticsearch"

    def __init__(
        self,
        *,
        host:       str = "localhost",
        port:       int = 9200,
        user:       str | None = None,
        password:   str | None = None,
        index:      str | None = None,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        overlap:    int = DEFAULT_OVERLAP,
    ) -> None:
        from elasticsearch import Elasticsearch

        scheme = "https" if int(port) == 443 else "http"
        kwargs: dict[str, Any] = {"hosts": [f"{scheme}://{host}:{port}"]}
        if user and password:
            kwargs["basic_auth"] = (user, password)
        elif password:
            kwargs["api_key"] = password

        self._es         = Elasticsearch(**kwargs, request_timeout=30)
        self._index      = index or "*"
        self._chunk_size = chunk_size
        self._overlap    = overlap

    def health_check(self) -> bool:
        try:
            return self._es.ping()
        except Exception:
            return False

    def normalise(self, *, query=None, tables=None, collections=None) -> list[NormalisedChunk]:
        from elasticsearch import helpers

        indices = collections or self._discover_indices()
        chunks: list[NormalisedChunk] = []

        es_query = {"query": {"query_string": {"query": query}}} if query else {"query": {"match_all": {}}}

        for idx_name in indices:
            logger.info("elasticsearch: reading index %s", idx_name)
            try:
                for i, hit in enumerate(helpers.scan(self._es, index=idx_name, query=es_query, scroll="5m")):
                    doc_id = hit.get("_id", str(i))
                    source = hit.get("_source", {})
                    text   = self._doc_to_text(idx_name, doc_id, source)
                    for chunk_idx, part in chunk_record(text, record_id=doc_id, collection=idx_name,
                                                        size=self._chunk_size, overlap=self._overlap):
                        chunks.append(NormalisedChunk(
                            source=self.SOURCE, database=self._index, collection=idx_name,
                            record_id=doc_id, chunk_index=chunk_idx, text=part,
                            metadata=_safe_metadata(source),
                        ))
            except Exception as e:
                logger.warning("elasticsearch: failed to read index %s: %s", idx_name, e)

        logger.info("elasticsearch: produced %d chunks", len(chunks))
        return chunks

    def _discover_indices(self) -> list[str]:
        try:
            aliases = self._es.indices.get_alias(index="*")
            return sorted(
                name for name in aliases.keys()
                if not any(name.startswith(p) for p in _SKIP_PREFIXES)
            )
        except Exception:
            return []

    def _doc_to_text(self, index: str, doc_id: str, source: dict[str, Any]) -> str:
        lines = [f"[Index: {index} | ID: {doc_id}]"]
        for key, val in source.items():
            if val is None:
                continue
            val_str = self._coerce_str(val)
            if val_str:
                lines.append(f"{key}: {val_str}")
        return "\n".join(lines)


def _safe_metadata(doc: dict[str, Any]) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    for k, v in doc.items():
        if isinstance(v, (str, int, float, bool)) or v is None:
            safe[k] = v
        else:
            safe[k] = str(v)
    return safe
