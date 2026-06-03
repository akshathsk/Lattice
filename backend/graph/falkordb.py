"""
FalkorDB implementation of GraphDBPlugin.

Storage layout
--------------
Graph name : ``lattice``  (matches the vector indexes created in startup.py)

Node labels
  :Chunk   — one per NormalisedChunk; carries the 768-dim embedding
  :Entity  — one per unique real-world entity; carries optional embedding

Relationship types (dynamic, driven by extraction output)
  :MENTIONS     — (:Chunk)  → (:Entity)
  :<REL_TYPE>   — (:Entity) → (:Entity)  e.g. PARTY_TO, GOVERNS …

Schema tracking (Redis sets, updated on every write)
  lattice:schema:labels    — known Entity types
  lattice:schema:rel_types — known relationship types

Vector indexes (created in startup.py, also idempotent here via create_indexes)
  Chunk.embedding   — dim=768, cosine
  Entity.embedding  — dim=768, cosine
"""

from __future__ import annotations

import logging
from typing import Any

import falkordb as fdb
import redis

from normalise.models import NormalisedChunk

from .base   import GraphDBPlugin
from .models import (
    Entity,
    Relation,
    ChunkResult,
    EntityResult,
    TraversalResult,
)

logger = logging.getLogger(__name__)

_GRAPH_NAME        = "lattice"
_SCHEMA_LABELS_KEY = "lattice:schema:labels"
_SCHEMA_RELS_KEY   = "lattice:schema:rel_types"
_EMBEDDING_DIM     = 768


class FalkorDBPlugin(GraphDBPlugin):
    """
    GraphDBPlugin backed by FalkorDB.

    Parameters
    ----------
    host       : FalkorDB / Redis host (default ``localhost``)
    port       : Redis port (default ``6379``)
    graph_name : Graph name inside FalkorDB (default ``lattice``)
    """

    def __init__(
        self,
        host:       str = "localhost",
        port:       int = 6379,
        graph_name: str = _GRAPH_NAME,
    ) -> None:
        self._host       = host
        self._port       = port
        self._graph_name = graph_name

        self._db    = fdb.FalkorDB(host=host, port=port)
        self._graph = self._db.select_graph(graph_name)
        self._redis = redis.Redis(host=host, port=port, decode_responses=True)

    # ── health ────────────────────────────────────────────────────────────────

    def health_check(self) -> bool:
        try:
            self._graph.query("RETURN 1")
            return True
        except Exception:
            return False

    # ── admin ─────────────────────────────────────────────────────────────────

    def create_indexes(self, rebuild: bool = False) -> None:
        """
        Ensure Chunk and Entity vector indexes exist.

        Parameters
        ----------
        rebuild : Drop-and-recreate even if the index already exists.
                  Use this after a bulk ingest — FalkorDB's HNSW index is
                  built on graph state at creation time and does not always
                  backfill nodes that receive embeddings via MERGE+SET later.
                  Calling create_indexes(rebuild=True) after the first ingest
                  guarantees all existing nodes are covered.
        """
        for label in ("Chunk", "Entity"):
            if rebuild:
                try:
                    self._graph.query(
                        f"DROP VECTOR INDEX FOR (n:{label}) ON (n.embedding)"
                    )
                    logger.info("Dropped vector index for :%s (rebuild)", label)
                except Exception:
                    pass  # didn't exist — fine

            try:
                self._graph.query(f"""
                    CREATE VECTOR INDEX FOR (n:{label}) ON (n.embedding)
                    OPTIONS {{dimension: {_EMBEDDING_DIM}, similarityFunction: 'cosine'}}
                """)
                logger.info("Created vector index for :%s", label)
            except Exception as e:
                if "already indexed" in str(e).lower():
                    logger.debug("Vector index for :%s already exists", label)
                else:
                    raise

    # ── schema ────────────────────────────────────────────────────────────────

    def get_schema(self) -> dict[str, Any]:
        labels    = sorted(self._redis.smembers(_SCHEMA_LABELS_KEY))
        rel_types = sorted(self._redis.smembers(_SCHEMA_RELS_KEY))
        return {"labels": labels, "rel_types": rel_types}

    def _register_label(self, label: str) -> None:
        self._redis.sadd(_SCHEMA_LABELS_KEY, label)

    def _register_rel_type(self, rel_type: str) -> None:
        self._redis.sadd(_SCHEMA_RELS_KEY, rel_type)

    # ── write: chunks ─────────────────────────────────────────────────────────

    def write_chunk(
        self,
        chunk:     NormalisedChunk,
        embedding: list[float],
    ) -> str:
        """
        Upsert a :Chunk node.  Uses MERGE on ``id`` so re-running the
        ingestion pipeline is idempotent.
        """
        self._graph.query(
            """
            MERGE (c:Chunk {id: $id})
            SET   c.source      = $source,
                  c.database    = $database,
                  c.collection  = $collection,
                  c.record_id   = $record_id,
                  c.chunk_index = $chunk_index,
                  c.text        = $text,
                  c.embedding   = vecf32($embedding)
            """,
            {
                "id":          chunk.id,
                "source":      chunk.source,
                "database":    chunk.database,
                "collection":  chunk.collection,
                "record_id":   chunk.record_id,
                "chunk_index": chunk.chunk_index,
                "text":        chunk.text,
                "embedding":   embedding,
            },
        )
        logger.debug("write_chunk %s", chunk.id)
        return chunk.id

    # ── write: entities ───────────────────────────────────────────────────────

    def write_entities(self, entities: list[Entity]) -> list[str]:
        """
        Upsert Entity nodes.  MERGE on stable ``id`` (sha256 of type+name).
        Registers each entity type in the schema label set.
        """
        ids: list[str] = []
        for entity in entities:
            params: dict[str, Any] = {
                "id":   entity.id,
                "name": entity.name,
                "type": entity.type,
            }

            if entity.embedding:
                self._graph.query(
                    """
                    MERGE (e:Entity {id: $id})
                    SET   e.name      = $name,
                          e.type      = $type,
                          e.embedding = vecf32($embedding)
                    """,
                    {**params, "embedding": entity.embedding},
                )
            else:
                self._graph.query(
                    """
                    MERGE (e:Entity {id: $id})
                    SET   e.name = $name,
                          e.type = $type
                    """,
                    params,
                )

            # Write any extra properties individually (avoids Cypher map issues)
            for k, v in entity.properties.items():
                try:
                    self._graph.query(
                        "MATCH (e:Entity {id: $id}) SET e[$k] = $v",
                        {"id": entity.id, "k": k, "v": str(v)},
                    )
                except Exception:
                    pass  # best-effort extra properties

            self._register_label(entity.type)
            ids.append(entity.id)
            logger.debug("write_entity %s (%s: %s)", entity.id, entity.type, entity.name)

        return ids

    # ── write: relations ──────────────────────────────────────────────────────

    def write_relations(self, relations: list[Relation]) -> None:
        """
        Upsert directed edges between Entity nodes.

        Relationship types are embedded in the query string (not parameterised)
        because openCypher does not support dynamic relationship-type labels in
        MERGE.  ``safe_type`` sanitises the string before interpolation.
        """
        for rel in relations:
            rel_type = rel.safe_type
            self._graph.query(
                f"""
                MATCH (a:Entity {{id: $src}}), (b:Entity {{id: $dst}})
                MERGE (a)-[r:{rel_type}]->(b)
                """,
                {"src": rel.source_id, "dst": rel.target_id},
            )
            self._register_rel_type(rel_type)
            logger.debug(
                "write_relation %s -[%s]-> %s",
                rel.source_id, rel_type, rel.target_id,
            )

    # ── write: mentions ───────────────────────────────────────────────────────

    def write_mentions(self, chunk_id: str, entity_ids: list[str]) -> None:
        """Create (:Chunk)-[:MENTIONS]->(:Entity) edges."""
        for eid in entity_ids:
            self._graph.query(
                """
                MATCH (c:Chunk  {id: $cid}),
                      (e:Entity {id: $eid})
                MERGE (c)-[:MENTIONS]->(e)
                """,
                {"cid": chunk_id, "eid": eid},
            )
        self._register_rel_type("MENTIONS")

    # ── read: entity fuzzy match ──────────────────────────────────────────────

    def fuzzy_match_entities(
        self,
        embedding: list[float],
        k:         int   = 5,
        threshold: float = 0.15,
    ) -> list[EntityResult]:
        """
        KNN search on Entity.embedding.

        Returns entities whose cosine *distance* from *embedding* is ≤
        *threshold* (0 = identical, 2 = opposite).  Default threshold 0.15
        keeps only close matches, reducing false-positive merges.
        """
        res = self._graph.query(
            """
            CALL db.idx.vector.queryNodes('Entity', 'embedding', $k, vecf32($vec))
            YIELD node, score
            WHERE score <= $threshold
            RETURN node.id, node.name, node.type, score
            """,
            {"k": k, "vec": embedding, "threshold": threshold},
        )
        return [
            EntityResult(
                entity_id = row[0],
                name      = row[1],
                type      = row[2],
                score     = row[3],
            )
            for row in res.result_set
        ]

    # ── read: chunks by entity ────────────────────────────────────────────────

    def get_chunks_mentioning(
        self,
        entity_ids: list[str],
        limit:      int = 20,
    ) -> list[ChunkResult]:
        """Return chunks that have a MENTIONS edge to any of the given entities."""
        res = self._graph.query(
            """
            MATCH (c:Chunk)-[:MENTIONS]->(e:Entity)
            WHERE e.id IN $ids
            RETURN DISTINCT c.id,
                            c.text,
                            c.source,
                            c.database,
                            c.collection,
                            c.record_id,
                            c.chunk_index
            LIMIT $limit
            """,
            {"ids": entity_ids, "limit": limit},
        )
        return [
            ChunkResult(
                chunk_id    = row[0],
                text        = row[1],
                source      = row[2],
                database    = row[3],
                collection  = row[4],
                record_id   = row[5],
                chunk_index = row[6],
                score       = 0.0,  # no vector score — ranked by the merger
            )
            for row in res.result_set
        ]

    # ── read: chunk vector search ─────────────────────────────────────────────

    def vector_search(
        self,
        embedding: list[float],
        k:         int = 5,
    ) -> list[ChunkResult]:
        """KNN search on Chunk.embedding — semantic retrieval for RAG."""
        res = self._graph.query(
            """
            CALL db.idx.vector.queryNodes('Chunk', 'embedding', $k, vecf32($vec))
            YIELD node, score
            RETURN node.id,
                   node.text,
                   node.source,
                   node.database,
                   node.collection,
                   node.record_id,
                   node.chunk_index,
                   score
            """,
            {"k": k, "vec": embedding},
        )
        return [
            ChunkResult(
                chunk_id    = row[0],
                text        = row[1],
                source      = row[2],
                database    = row[3],
                collection  = row[4],
                record_id   = row[5],
                chunk_index = row[6],
                score       = row[7],
            )
            for row in res.result_set
        ]

    # ── read: graph traversal ─────────────────────────────────────────────────

    def traverse(
        self,
        entity_id: str,
        hops:      int = 2,
    ) -> TraversalResult:
        """
        Return all nodes and edges reachable within *hops* from *entity_id*.

        Traverses in both directions (undirected) so callers get the full
        local neighbourhood regardless of edge orientation.

        Node dicts include all stored properties except ``embedding``.
        Edge dicts carry resolved names/types for both endpoints so callers
        don't need to do a separate id→name lookup.
        """
        # ── Nodes — all properties except the embedding vector ────────────────
        node_res = self._graph.query(
            f"""
            MATCH (seed:Entity {{id: $id}})-[*1..{hops}]-(n:Entity)
            WITH DISTINCT n
            WITH n,
                 [k IN keys(n)
                  WHERE k <> 'embedding' AND k <> 'id'
                        AND k <> 'name'  AND k <> 'type'] AS attr_keys
            RETURN n.id, n.name, n.type, attr_keys,
                   [k IN attr_keys | n[k]] AS attr_vals
            """,
            {"id": entity_id},
        )
        nodes = []
        for row in node_res.result_set:
            attrs = dict(zip(row[3], row[4])) if row[3] else {}
            nodes.append({"id": row[0], "name": row[1], "type": row[2], **attrs})

        # ── Edges — all edges between subgraph nodes (not just seed-adjacent) ──
        # Collect the IDs of every node in the subgraph (seed + reachable nodes),
        # then match all edges whose both endpoints are in that set.
        edge_res = self._graph.query(
            f"""
            MATCH (seed:Entity {{id: $id}})-[*1..{hops}]-(n:Entity)
            WITH collect(DISTINCT n.id) + [$id] AS all_ids
            MATCH (a:Entity)-[r]->(b:Entity)
            WHERE a.id IN all_ids AND b.id IN all_ids
            RETURN a.id, a.name, a.type, type(r), b.id, b.name, b.type
            """,
            {"id": entity_id},
        )
        edges = [
            {
                "src":      row[0],
                "src_name": row[1],
                "src_type": row[2],
                "type":     row[3],
                "dst":      row[4],
                "dst_name": row[5],
                "dst_type": row[6],
            }
            for row in edge_res.result_set
        ]

        return TraversalResult(
            seed_id = entity_id,
            depth   = hops,
            nodes   = nodes,
            edges   = edges,
        )
