"""
MongoDB normaliser.

Reads documents from a MongoDB database and converts each document into one
or more NormalisedChunk objects.

Document → text conversion
--------------------------
Documents are rendered field-by-field, with nested dicts and lists
recursively flattened into readable prose.  The ``body`` / ``content`` /
``text`` field (if present) is placed last so it dominates the chunk.

Example output for an email document::

    [Collection: emails | ID: 6789abc…]
    type: email
    subject: Re: Acme Corp MSA — Liability Cap Concern
    from: jane.ceo@ourcompany.com
    to: legal@acme.com, clo@ourcompany.com
    date: 2022-02-14
    related_contract: Master Services Agreement — Acme Corp
    related_party: Acme Corp
    body:
    Jane,

    Following our call I wanted to put in writing our position on the
    liability cap …

Usage
-----
    from normalise.mongo import MongoNormaliser

    n = MongoNormaliser(host="localhost", port=27017, database="contracts_docs")

    # Read every collection
    chunks = n.normalise()

    # Specific collections
    chunks = n.normalise(collections=["emails", "memos"])

    # Filter applied to every collection
    chunks = n.normalise(query={"related_party": "Acme Corp"})

    # Filter on a specific collection
    chunks = n.normalise(collections=["emails"],
                         query={"related_party": "Acme Corp"})
"""

from __future__ import annotations

import logging
from typing import Any

import pymongo
from bson import ObjectId

from .base    import BaseNormaliser
from .chunker import chunk_record, DEFAULT_CHUNK_SIZE, DEFAULT_OVERLAP
from .models  import NormalisedChunk

logger = logging.getLogger(__name__)

# Fields whose content should be placed at the end of the text block
# (they tend to be long and should dominate the chunk if splitting occurs).
_BODY_FIELDS = {"body", "content", "text", "description", "summary", "findings"}

# Fields to omit from text entirely (internal Mongo fields, binary data …).
_SKIP_FIELDS = {"_id", "__v"}

# System collections created by MongoDB itself.
_SKIP_COLLECTIONS = {"system.views", "system.buckets"}


class MongoNormaliser(BaseNormaliser):
    """Normalise documents from a MongoDB database into NormalisedChunk objects."""

    SOURCE = "mongo"

    def __init__(
        self,
        *,
        host:       str = "localhost",
        port:       int = 27017,
        database:   str,
        username:   str | None = None,
        password:   str | None = None,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        overlap:    int = DEFAULT_OVERLAP,
    ) -> None:
        kwargs: dict[str, Any] = dict(host=host, port=port)
        if username and password:
            kwargs.update(username=username, password=password)
        self._client_kwargs = kwargs
        self._dbname        = database
        self._chunk_size    = chunk_size
        self._overlap       = overlap

    # ── public API ────────────────────────────────────────────────────────────

    def health_check(self) -> bool:
        try:
            client = self._connect()
            client.server_info()
            client.close()
            return True
        except Exception:
            return False

    def normalise(
        self,
        *,
        query:       dict[str, Any] | None = None,
        tables:      list[str] | None      = None,   # ignored for Mongo
        collections: list[str] | None      = None,
    ) -> list[NormalisedChunk]:
        """
        Parameters
        ----------
        query       : PyMongo filter dict applied to every targeted collection.
                      ``None`` → ``{}`` (match all documents).
        collections : Collection names to read.  When omitted, every collection
                      in the database is read.
        """
        filter_doc = query or {}
        chunks: list[NormalisedChunk] = []

        client = self._connect()
        try:
            db = client[self._dbname]
            target_collections = collections or self._discover_collections(db)

            for coll_name in target_collections:
                logger.info("mongo: reading collection %s (filter=%s)", coll_name, filter_doc)
                chunks.extend(
                    self._read_collection(db[coll_name], coll_name, filter_doc)
                )
        finally:
            client.close()

        logger.info("mongo: produced %d chunks total", len(chunks))
        return chunks

    # ── internal ──────────────────────────────────────────────────────────────

    def _connect(self) -> pymongo.MongoClient:
        return pymongo.MongoClient(
            **self._client_kwargs,
            serverSelectionTimeoutMS=5_000,
        )

    def _discover_collections(self, db) -> list[str]:
        """Return all non-system collection names, sorted."""
        return sorted(
            name
            for name in db.list_collection_names()
            if name not in _SKIP_COLLECTIONS
        )

    def _read_collection(
        self,
        collection,
        coll_name:  str,
        filter_doc: dict[str, Any],
    ) -> list[NormalisedChunk]:
        chunks: list[NormalisedChunk] = []

        for doc in collection.find(filter_doc):
            record_id = str(doc.get("_id", "unknown"))
            text      = self._doc_to_text(coll_name, doc)

            for idx, part in chunk_record(
                text,
                record_id=record_id,
                collection=coll_name,
                size=self._chunk_size,
                overlap=self._overlap,
            ):
                chunks.append(
                    NormalisedChunk(
                        source      = self.SOURCE,
                        database    = self._dbname,
                        collection  = coll_name,
                        record_id   = record_id,
                        chunk_index = idx,
                        text        = part,
                        metadata    = self._safe_metadata(doc),
                    )
                )

        return chunks

    # ── text assembly ─────────────────────────────────────────────────────────

    def _doc_to_text(self, collection: str, doc: dict[str, Any]) -> str:
        """
        Convert a MongoDB document to a readable text block.

        Short fields come first; long body/content fields come last so that
        if the text is split into multiple chunks the header context (type,
        subject, parties …) appears in chunk 0 and the body dominates later
        chunks.
        """
        oid = doc.get("_id", "")
        header = f"[Collection: {collection} | ID: {oid}]"

        lead_lines:  list[str] = [header]
        trail_lines: list[str] = []

        for key, val in doc.items():
            if key in _SKIP_FIELDS or val is None:
                continue

            val_str = self._coerce_str(val)
            if not val_str:
                continue

            if key in _BODY_FIELDS:
                trail_lines.append(f"{key}:\n{val_str}")
            else:
                lead_lines.append(f"{key}: {val_str}")

        return "\n".join(lead_lines + trail_lines)

    @staticmethod
    def _safe_metadata(doc: dict[str, Any]) -> dict[str, Any]:
        """Return a JSON-serialisable copy of the document."""
        import datetime

        safe: dict[str, Any] = {}
        for k, v in doc.items():
            if isinstance(v, ObjectId):
                safe[k] = str(v)
            elif isinstance(v, (datetime.date, datetime.datetime)):
                safe[k] = v.isoformat()
            elif isinstance(v, (str, int, float, bool)) or v is None:
                safe[k] = v
            elif isinstance(v, list):
                safe[k] = [str(i) if not isinstance(i, (str, int, float, bool)) else i for i in v]
            else:
                safe[k] = str(v)
        return safe
