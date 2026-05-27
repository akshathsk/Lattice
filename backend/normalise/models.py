"""
Normalised chunk — the single output type produced by every normaliser.

Every record from any data source (SQL row, Mongo document, file paragraph …)
is ultimately expressed as one or more NormalisedChunk objects before being
handed to the embedding + extraction pipeline.
"""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, Field


class NormalisedChunk(BaseModel):
    """
    A single unit of text ready for embedding and entity extraction.

    Fields
    ------
    id          : Unique chunk identifier (UUID4).
    source      : Connector type — ``"postgres"`` | ``"mongo"`` | ``"file"`` …
    database    : Database / file-system root the record came from.
    collection  : Table name (SQL) or collection name (Mongo) or file path.
    record_id   : Primary-key / ``_id`` of the originating record (as string).
    chunk_index : 0-based position when one record splits into many chunks.
    text        : The normalised text passed to the embedding model.
    metadata    : Passthrough bag of typed fields from the original record
                  (dates, enums, numeric values …) preserved for downstream
                  filtering without re-querying the source DB.
    """

    id:          str            = Field(default_factory=lambda: str(uuid.uuid4()))
    source:      str            # "postgres" | "mongo" | "file"
    database:    str            # db name or file root
    collection:  str            # table / collection / file path
    record_id:   str            # original pk / _id as string
    chunk_index: int            # 0-based within this record
    text:        str            # clean text for embedding + extraction
    metadata:    dict[str, Any] = Field(default_factory=dict)

    # ── helpers ───────────────────────────────────────────────────────────────

    @property
    def chunk_key(self) -> str:
        """Stable key for deduplication: source + collection + record + index."""
        return f"{self.source}:{self.collection}:{self.record_id}:{self.chunk_index}"

    def __repr__(self) -> str:
        preview = self.text[:60].replace("\n", " ")
        return (
            f"NormalisedChunk({self.source}/{self.collection}#{self.record_id}"
            f"[{self.chunk_index}] {preview!r}…)"
        )
