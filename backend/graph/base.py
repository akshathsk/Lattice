"""
Abstract base class for graph database plugins.

Any graph backend (FalkorDB, Neo4j, Amazon Neptune …) implements this
interface.  The extraction pipeline and chatbot only ever call methods
defined here — they are completely decoupled from the storage engine.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from .models import (
    Entity,
    Relation,
    ChunkResult,
    EntityResult,
    TraversalResult,
)

# Import here so callers only need to import from graph.base
from normalise.models import NormalisedChunk  # noqa: F401


class GraphDBPlugin(ABC):
    """
    Interface every graph backend must satisfy.

    Write path (called by the extraction pipeline):
        write_chunk      — store a chunk node + its vector embedding
        write_entities   — upsert entity nodes (dedup by stable ID)
        write_relations  — upsert directed edges between entities
        write_mentions   — link a chunk to the entities it mentions

    Read path (called by graph-context fetcher and RAG retriever):
        get_schema            — current node labels + relationship types
        fuzzy_match_entities  — KNN on entity embeddings (dedup / linking)
        vector_search         — KNN on chunk embeddings (semantic retrieval)
        traverse              — N-hop subgraph from a seed entity

    Admin:
        create_indexes — ensure vector indexes exist (idempotent)
        health_check   — True if the backend is reachable
    """

    # ── write ─────────────────────────────────────────────────────────────────

    @abstractmethod
    def write_chunk(
        self,
        chunk:     NormalisedChunk,
        embedding: list[float],
    ) -> str:
        """
        Upsert a Chunk node carrying the text + vector embedding.

        Returns the chunk's graph node ID (same as ``chunk.id``).
        """

    @abstractmethod
    def write_entities(self, entities: list[Entity]) -> list[str]:
        """
        Upsert a list of Entity nodes.

        Returns the list of entity IDs in the same order as *entities*.
        """

    @abstractmethod
    def write_relations(self, relations: list[Relation]) -> None:
        """
        Upsert directed edges between Entity nodes.

        Entities referenced by ``relation.source_id`` / ``relation.target_id``
        must already exist in the graph (call ``write_entities`` first).
        """

    @abstractmethod
    def write_mentions(self, chunk_id: str, entity_ids: list[str]) -> None:
        """
        Create ``(:Chunk)-[:MENTIONS]->(:Entity)`` edges.

        Both the chunk and every entity must already exist in the graph.
        """

    # ── read ──────────────────────────────────────────────────────────────────

    @abstractmethod
    def get_schema(self) -> dict[str, Any]:
        """
        Return the current graph schema.

        Shape::

            {
                "labels":    ["Person", "Organization", …],
                "rel_types": ["PARTY_TO", "GOVERNS", …],
            }
        """

    @abstractmethod
    def fuzzy_match_entities(
        self,
        embedding: list[float],
        k:         int = 5,
        threshold: float = 0.15,   # cosine distance — lower = more similar
    ) -> list[EntityResult]:
        """
        Return the *k* most similar existing entities by embedding distance.

        Used by the extraction pipeline to detect duplicate / co-referent
        entities before writing new ones.
        """

    @abstractmethod
    def vector_search(
        self,
        embedding: list[float],
        k:         int = 5,
    ) -> list[ChunkResult]:
        """
        Return the *k* most similar chunks by embedding distance.

        Used by the RAG retriever to surface relevant context.
        """

    @abstractmethod
    def traverse(
        self,
        entity_id: str,
        hops:      int = 2,
    ) -> TraversalResult:
        """
        Return a subgraph reachable within *hops* edges from *entity_id*.

        Used by the graph-context fetcher and RAG graph retriever.
        """

    # ── admin ─────────────────────────────────────────────────────────────────

    @abstractmethod
    def create_indexes(self) -> None:
        """Ensure all required vector indexes exist (idempotent)."""

    @abstractmethod
    def health_check(self) -> bool:
        """Return True if the underlying store is reachable."""
