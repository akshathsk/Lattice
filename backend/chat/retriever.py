"""
RAG retriever — two-path retrieval over the knowledge graph.

Path A — vector search on chunk embeddings
    embed query → KNN on Chunk.embedding → top-K semantically similar chunks

Path B — entity-anchored graph traversal
    embed query → KNN on Entity.embedding → matched entity nodes
                → get_chunks_mentioning()  → source chunks for those entities
                → traverse()               → N-hop subgraph (nodes + edges)

The two chunk sets are merged and ranked.  Chunks that appear in both paths
get a score boost — they are both semantically similar *and* structurally
connected to query-relevant entities, making them the most reliable context.

Usage
-----
    from chat.retriever import Retriever
    from graph import get_graph_plugin

    retriever = Retriever(get_graph_plugin())
    result    = retriever.retrieve("What are Acme Corp's payment obligations?")

    for chunk in result.chunks:
        print(chunk.score, chunk.text[:80])
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from extraction.embedder import embed_text
from graph.models import ChunkResult, EntityResult

if TYPE_CHECKING:
    from graph.base import GraphDBPlugin

logger = logging.getLogger(__name__)

# Score assigned to graph-only chunks (no vector score available).
# Chosen to sit below a strong vector hit (~0.8) but above a weak one (~0.4).
_GRAPH_BASE_SCORE = 0.5

# Bonus added when a chunk appears in both paths.
_BOTH_PATHS_BOOST = 0.2


# ── output models ─────────────────────────────────────────────────────────────

@dataclass
class RankedChunk:
    """A deduplicated, scored chunk ready to pass to the LLM."""
    chunk_id:   str
    text:       str
    source:     str
    collection: str
    record_id:  str
    score:      float
    via:        list[str]   # ["vector"], ["graph"], or ["vector", "graph"]


@dataclass
class RetrievalResult:
    """Full retrieval output — chunks + graph context."""
    query:           str
    chunks:          list[RankedChunk]          # ranked, deduplicated
    entity_matches:  list[EntityResult]         # entities matched in Path B
    subgraph_nodes:  list[dict]                 # nodes from N-hop traversal
    subgraph_edges:  list[dict]                 # edges from N-hop traversal


# ── retriever ─────────────────────────────────────────────────────────────────

class Retriever:
    """
    Two-path RAG retriever.

    Parameters
    ----------
    graph            : GraphDBPlugin to query.
    chunk_k          : Number of chunks to return from vector search (Path A).
    entity_k         : Number of entity matches to use as graph anchors (Path B).
    entity_threshold : Cosine distance cutoff for entity matching (0=identical).
                       Higher = more permissive.  0.55 is appropriate for RAG
                       — query sentences sit ~0.4+ away from short entity names
                       in sentence-transformer embedding space, so the ingest
                       dedup threshold (0.25) is far too tight here.
    hops             : Traversal depth from matched entities.
    """

    def __init__(
        self,
        graph:            "GraphDBPlugin",
        chunk_k:          int   = 6,
        entity_k:         int   = 5,
        entity_threshold: float = 0.55,
        hops:             int   = 2,
    ) -> None:
        self._graph            = graph
        self._chunk_k          = chunk_k
        self._entity_k         = entity_k
        self._entity_threshold = entity_threshold
        self._hops             = hops

    # ── public ────────────────────────────────────────────────────────────────

    def retrieve(self, query: str) -> RetrievalResult:
        """
        Run both retrieval paths and return merged, ranked context.

        The query is embedded once and reused for both KNN calls.
        """
        logger.info("Retriever: query=%r", query)
        embedding = embed_text(query)

        # ── Path A: semantic chunk search ─────────────────────────────────────
        vector_chunks = self._graph.vector_search(embedding, k=self._chunk_k)
        logger.debug("Path A: %d chunks", len(vector_chunks))

        # ── Path B: entity-anchored graph retrieval ───────────────────────────
        entity_hits = self._graph.fuzzy_match_entities(
            embedding,
            k         = self._entity_k,
            threshold = self._entity_threshold,
        )
        logger.debug("Path B: %d entity matches", len(entity_hits))

        graph_chunks:    list[ChunkResult] = []
        subgraph_nodes:  list[dict]        = []
        subgraph_edges:  list[dict]        = []

        if entity_hits:
            entity_ids = [e.entity_id for e in entity_hits]

            # Chunks that mention the matched entities
            graph_chunks = self._graph.get_chunks_mentioning(entity_ids)
            logger.debug("Path B: %d source chunks for matched entities", len(graph_chunks))

            # N-hop subgraph from each matched entity (for LLM context)
            seen_nodes: set[str]               = set()
            seen_edges: set[tuple[str, str, str]] = set()

            for entity_id in entity_ids:
                try:
                    traversal = self._graph.traverse(entity_id, hops=self._hops)
                    for node in traversal.nodes:
                        if node["id"] not in seen_nodes:
                            seen_nodes.add(node["id"])
                            subgraph_nodes.append(node)
                    for edge in traversal.edges:
                        key = (edge["src"], edge["type"], edge["dst"])
                        if key not in seen_edges:
                            seen_edges.add(key)
                            subgraph_edges.append(edge)
                except Exception as e:
                    logger.debug("Traversal failed for %s: %s", entity_id, e)

        # ── Merge + rank ──────────────────────────────────────────────────────
        ranked = _merge(vector_chunks, graph_chunks)
        logger.info(
            "Retriever: %d ranked chunks | %d entity matches | %d subgraph edges",
            len(ranked), len(entity_hits), len(subgraph_edges),
        )

        return RetrievalResult(
            query          = query,
            chunks         = ranked,
            entity_matches = entity_hits,
            subgraph_nodes = subgraph_nodes,
            subgraph_edges = subgraph_edges,
        )


# ── helpers ───────────────────────────────────────────────────────────────────

def _merge(
    vector_chunks: list[ChunkResult],
    graph_chunks:  list[ChunkResult],
) -> list[RankedChunk]:
    """
    Deduplicate and rank chunks from both paths.

    Scoring:
      Path A score = 1 - cosine_distance   (similarity, higher = better)
      Path B score = _GRAPH_BASE_SCORE     (flat; no vector score available)
      Both paths   = Path A score + _BOTH_PATHS_BOOST
    """
    by_id: dict[str, RankedChunk] = {}

    for c in vector_chunks:
        sim = 1.0 - c.score  # cosine distance → similarity
        by_id[c.chunk_id] = RankedChunk(
            chunk_id   = c.chunk_id,
            text       = c.text,
            source     = c.source,
            collection = c.collection,
            record_id  = c.record_id,
            score      = sim,
            via        = ["vector"],
        )

    for c in graph_chunks:
        if c.chunk_id in by_id:
            # Seen in both paths — boost
            by_id[c.chunk_id].score += _BOTH_PATHS_BOOST
            by_id[c.chunk_id].via.append("graph")
        else:
            by_id[c.chunk_id] = RankedChunk(
                chunk_id   = c.chunk_id,
                text       = c.text,
                source     = c.source,
                collection = c.collection,
                record_id  = c.record_id,
                score      = _GRAPH_BASE_SCORE,
                via        = ["graph"],
            )

    return sorted(by_id.values(), key=lambda x: x.score, reverse=True)
