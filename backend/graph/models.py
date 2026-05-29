"""
Shared data models for the graph layer.

These are the types that flow between the extraction pipeline and the
GraphDBPlugin — they are source-agnostic and graph-agnostic.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

from pydantic import BaseModel, Field


def _stable_id(type_: str, name: str) -> str:
    """
    Deterministic 16-char hex ID for an entity.

    Two mentions of the same concept (same type + normalised name) always
    produce the same ID, enabling upsert/MERGE without a prior lookup.
    """
    key = f"{type_.lower().strip()}:{name.lower().strip()}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def _safe_rel_type(raw: str) -> str:
    """
    Sanitise a relationship type string for use as a Cypher label.

    Strips leading/trailing whitespace, uppercases, replaces spaces and
    hyphens with underscores, removes any character that isn't A-Z / 0-9 / _.
    """
    s = raw.strip().upper()
    s = re.sub(r"[\s\-]+", "_", s)
    s = re.sub(r"[^A-Z0-9_]", "", s)
    return s or "RELATED_TO"


# ── entity ────────────────────────────────────────────────────────────────────

class Entity(BaseModel):
    """
    A node to be written to (or merged with) the graph.

    ``id`` is derived deterministically from *type* + *name* so that the same
    real-world entity always resolves to the same graph node regardless of
    which chunk or extraction run produced it.
    """

    id:         str                     # stable hash — set via make()
    name:       str                     # canonical surface form
    type:       str                     # Person, Organization, Clause …
    embedding:  list[float] | None = None  # 768-dim when available
    properties: dict[str, Any]     = Field(default_factory=dict)

    @classmethod
    def make(
        cls,
        name:       str,
        type_:      str,
        embedding:  list[float] | None = None,
        properties: dict[str, Any]     | None = None,
    ) -> "Entity":
        return cls(
            id         = _stable_id(type_, name),
            name       = name,
            type       = type_,
            embedding  = embedding,
            properties = properties or {},
        )


# ── relation ──────────────────────────────────────────────────────────────────

class Relation(BaseModel):
    """
    A directed edge between two Entity nodes.

    ``type`` is sanitised to a valid Cypher relationship-type string before
    being written (spaces → underscores, uppercased).
    """

    source_id:  str               # Entity.id of the head node
    target_id:  str               # Entity.id of the tail node
    type:       str               # e.g. PARTY_TO, GOVERNS, REFERENCES
    properties: dict[str, Any] = Field(default_factory=dict)

    @property
    def safe_type(self) -> str:
        return _safe_rel_type(self.type)


# ── search / retrieval results ────────────────────────────────────────────────

class ChunkResult(BaseModel):
    """A chunk returned by vector search, ranked by similarity score."""

    chunk_id:    str
    score:       float
    text:        str
    source:      str
    database:    str
    collection:  str
    record_id:   str
    chunk_index: int


class EntityResult(BaseModel):
    """An entity returned by fuzzy-match / vector search on entity embeddings."""

    entity_id: str
    name:      str
    type:      str
    score:     float


class TraversalResult(BaseModel):
    """
    Subgraph returned by an N-hop traversal from a seed entity.

    ``nodes``  : list of ``{"id": …, "name": …, "type": …}`` dicts.
    ``edges``  : list of ``{"src": …, "dst": …, "type": …}`` dicts.
    ``depth``  : the hop count used for the traversal.
    """

    seed_id: str
    depth:   int
    nodes:   list[dict[str, Any]] = Field(default_factory=list)
    edges:   list[dict[str, Any]] = Field(default_factory=list)
