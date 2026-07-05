"""
REST API normaliser — fetches JSON from any HTTP endpoint and converts each
item in the response to NormalisedChunks.

json_path
---------
Dot-notation path into the response to locate the list of records.
  ""          → use the root (works if the response is already a list)
  "data"      → response["data"]
  "data.items"→ response["data"]["items"]

If the resolved value is a dict, it is wrapped in a single-element list.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from .base    import BaseNormaliser
from .chunker import chunk_record, DEFAULT_CHUNK_SIZE, DEFAULT_OVERLAP
from .models  import NormalisedChunk

logger = logging.getLogger(__name__)


class RestApiNormaliser(BaseNormaliser):
    SOURCE = "rest"

    def __init__(
        self,
        *,
        url:         str,
        method:      str = "GET",
        auth_header: str | None = None,
        json_path:   str | None = None,
        body:        dict | None = None,
        chunk_size:  int = DEFAULT_CHUNK_SIZE,
        overlap:     int = DEFAULT_OVERLAP,
    ) -> None:
        self._url         = url
        self._method      = method.upper()
        self._headers     = {"Authorization": auth_header} if auth_header else {}
        self._json_path   = json_path or ""
        self._body        = body
        self._chunk_size  = chunk_size
        self._overlap     = overlap

    def health_check(self) -> bool:
        try:
            with httpx.Client(timeout=10) as client:
                r = client.request(self._method, self._url, headers=self._headers)
                return r.status_code < 500
        except Exception:
            return False

    def normalise(self, *, query=None, tables=None, collections=None) -> list[NormalisedChunk]:
        with httpx.Client(timeout=60) as client:
            r = client.request(
                self._method, self._url,
                headers=self._headers,
                json=self._body,
            )
            r.raise_for_status()
            data = r.json()

        items = _extract_path(data, self._json_path)
        if isinstance(items, dict):
            items = [items]
        elif not isinstance(items, list):
            items = [{"value": items}]

        chunks: list[NormalisedChunk] = []
        for i, item in enumerate(items):
            record_id = str(item.get("id") or item.get("_id") or i)
            text = _item_to_text(item)
            for idx, part in chunk_record(text, record_id=record_id, collection="response",
                                          size=self._chunk_size, overlap=self._overlap):
                chunks.append(NormalisedChunk(
                    source=self.SOURCE, database=self._url, collection="response",
                    record_id=record_id, chunk_index=idx, text=part,
                    metadata=_safe_metadata(item),
                ))

        logger.info("rest: produced %d chunks from %d items", len(chunks), len(items))
        return chunks


# ── helpers ───────────────────────────────────────────────────────────────────

def _extract_path(data: Any, path: str) -> Any:
    if not path:
        return data
    for key in path.split("."):
        if isinstance(data, dict):
            data = data.get(key, {})
        else:
            return data
    return data


def _item_to_text(item: Any) -> str:
    if isinstance(item, dict):
        lines = []
        for k, v in item.items():
            if v is None:
                continue
            if isinstance(v, (dict, list)):
                lines.append(f"{k}: {str(v)[:200]}")
            else:
                lines.append(f"{k}: {v}")
        return "\n".join(lines)
    return str(item)


def _safe_metadata(item: Any) -> dict[str, Any]:
    if not isinstance(item, dict):
        return {}
    safe: dict[str, Any] = {}
    for k, v in item.items():
        if isinstance(v, (str, int, float, bool)) or v is None:
            safe[k] = v
        else:
            safe[k] = str(v)
    return safe
