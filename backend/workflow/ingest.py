"""
Ingest pipeline — end-to-end data ingestion into the knowledge graph.

Wires together every stage in order:

    Data source (Postgres / Mongo / …)
        │
        ▼  normalise/
    NormalisedChunk[]          ← read + chunk source records
        │
        ▼  extraction/embedder
    embeddings[]               ← 768-dim vector per chunk (batched)
        │
        ├─ write_chunk()       ← Chunk node + embedding → FalkorDB
        │
        ▼  extraction/spacy_extractor
    SpacyResult                ← NER + SVO per chunk
        │
        ▼  extraction/gliner_extractor
    GlinerResult               ← zero-shot NER using live schema
        │
        ▼  extraction/graph_context
    GraphContext               ← existing schema + similar entities
        │
        ▼  extraction/llm_extractor
    Entity[], Relation[]       ← GPT-4o structured extraction
        │
        ├─ embed entities      ← 768-dim vector per entity name
        ├─ write_entities()    ← Entity nodes → FalkorDB (MERGE)
        ├─ write_relations()   ← edges → FalkorDB (MERGE)
        └─ write_mentions()    ← (:Chunk)-[:MENTIONS]->(:Entity)

Usage
-----
    from workflow.ingest import IngestPipeline

    pipeline = IngestPipeline()

    # Ingest everything from a source
    summary = pipeline.run("postgres")
    summary = pipeline.run("mongo")

    # Specific tables / collections
    summary = pipeline.run("postgres", tables=["contracts", "clauses"])
    summary = pipeline.run("mongo", collections=["emails", "memos"])

    # Custom query
    summary = pipeline.run("postgres",
                           query="SELECT * FROM contracts WHERE status='active'")
    summary = pipeline.run("mongo",
                           query={"related_party": "Acme Corp"},
                           collections=["emails"])

    # Ingest all configured sources in one call
    summary = pipeline.run_all()

    print(summary)
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Generator

from dotenv import load_dotenv

# ── env ───────────────────────────────────────────────────────────────────────
_env = Path(__file__).parent.parent / ".env"
if _env.exists():
    load_dotenv(_env)

# ── imports ───────────────────────────────────────────────────────────────────
from extraction.embedder         import embed_chunks, embed_texts
from extraction.spacy_extractor  import SpacyExtractor
from extraction.gliner_extractor import GlinerExtractor
from extraction.graph_context    import GraphContextFetcher
from extraction.llm_extractor    import LLMExtractor
from graph                       import get_graph_plugin, GraphDBPlugin
from normalise                   import get_normaliser

logger = logging.getLogger(__name__)


# ── summary model ─────────────────────────────────────────────────────────────

@dataclass
class ChunkStats:
    source:     str
    collection: str
    record_id:  str
    entities:   int
    relations:  int
    merged:     int   # entities merged with existing nodes
    error:      str | None = None


@dataclass
class IngestSummary:
    """Returned by every pipeline.run() call."""
    source:          str
    total_chunks:    int = 0
    ok_chunks:       int = 0
    failed_chunks:   int = 0
    total_entities:  int = 0
    total_relations: int = 0
    total_merged:    int = 0
    elapsed_s:       float = 0.0
    chunk_stats:     list[ChunkStats] = field(default_factory=list)

    def __str__(self) -> str:
        lines = [
            f"Ingest summary — source: {self.source}",
            f"  chunks     : {self.ok_chunks}/{self.total_chunks} ok"
            + (f"  ({self.failed_chunks} failed)" if self.failed_chunks else ""),
            f"  entities   : {self.total_entities}  (merged: {self.total_merged})",
            f"  relations  : {self.total_relations}",
            f"  elapsed    : {self.elapsed_s:.1f}s",
        ]
        if self.failed_chunks:
            lines.append("  failures:")
            for cs in self.chunk_stats:
                if cs.error:
                    lines.append(f"    {cs.source}/{cs.collection}#{cs.record_id}: {cs.error}")
        return "\n".join(lines)


# ── pipeline ──────────────────────────────────────────────────────────────────

class IngestPipeline:
    """
    End-to-end ingest pipeline.

    Parameters
    ----------
    graph        : GraphDBPlugin to write to.  Defaults to the plugin
                   selected by the GRAPH_DB_PLUGIN env var (falkordb).
    llm_extractor: LLMExtractor instance.  Defaults to a new one built
                   from OPENAI_API_KEY / OPENAI_MODEL env vars.
    """

    def __init__(
        self,
        graph:         GraphDBPlugin | None = None,
        llm_extractor: LLMExtractor  | None = None,
    ) -> None:
        self._graph   = graph         or get_graph_plugin()
        self._spacy   = SpacyExtractor()
        self._gliner  = GlinerExtractor(threshold=0.5)
        self._fetcher = GraphContextFetcher(self._graph)
        self._llm     = llm_extractor or LLMExtractor()

    # ── public ────────────────────────────────────────────────────────────────

    def run(
        self,
        source: str,
        *,
        tables:      list[str] | None       = None,
        collections: list[str] | None       = None,
        query:       str | dict | None      = None,
        normaliser_kwargs: dict[str, Any]   = {},
    ) -> IngestSummary:
        """
        Ingest from one source.

        Parameters
        ----------
        source      : ``"postgres"`` or ``"mongo"``.
        tables      : (postgres) table names to read; None = all tables.
        collections : (mongo)    collection names; None = all collections.
        query       : (postgres) raw SELECT string, or
                      (mongo)    filter dict applied to every collection.
        normaliser_kwargs : Extra kwargs forwarded to the normaliser
                            constructor (override env-based defaults).
        """
        logger.info("Ingest starting — source=%s", source)
        t0 = time.time()

        # Build normaliser from env + any overrides
        cfg = {**_source_config(source), **normaliser_kwargs}
        normaliser = get_normaliser(source, **cfg)

        if not normaliser.health_check():
            raise RuntimeError(f"Source {source!r} is not reachable — check connection settings")

        # Fetch and chunk all records
        logger.info("Normalising %s …", source)
        chunks = normaliser.normalise(
            query       = query,
            tables      = tables,
            collections = collections,
        )
        logger.info("  %d chunks produced", len(chunks))

        summary = self._process_chunks(chunks, source=source)
        summary.elapsed_s = time.time() - t0
        logger.info("Ingest complete — %s", summary)
        return summary

    def stream_run(
        self,
        source: str,
        *,
        tables:            list[str] | None     = None,
        collections:       list[str] | None     = None,
        query:             str | dict | None    = None,
        normaliser_kwargs: dict[str, Any]       = {},
    ) -> Generator[str, None, None]:
        """
        Like ``run()`` but yields SSE events (``data: {...}\\n\\n``) so callers
        can stream live progress to the client.

        Event types
        -----------
        {"t":"start",    "total": N, "source": "..."}
        {"t":"progress", "current": i, "total": N,
                         "collection": "...", "record_id": "...",
                         "entities": N, "relations": N, "merged": N,
                         "error": null|"...",
                         "total_entities": N, "total_relations": N,
                         "ok_chunks": N, "failed_chunks": N}
        {"t":"reindex"}
        {"t":"done",     "source": "...", "ok_chunks": N, ...}
        {"t":"error",    "message": "..."}
        """
        def _sse(data: dict) -> str:
            return f"data: {json.dumps(data)}\n\n"

        logger.info("Ingest starting (stream) — source=%s", source)
        t0 = time.time()

        cfg = {**_source_config(source), **normaliser_kwargs}
        normaliser = get_normaliser(source, **cfg)

        if not normaliser.health_check():
            yield _sse({"t": "error", "message": f"Source {source!r} not reachable — check connection"})
            return

        logger.info("Normalising %s …", source)
        chunks = normaliser.normalise(
            query       = query,
            tables      = tables,
            collections = collections,
        )
        logger.info("  %d chunks produced", len(chunks))

        yield _sse({"t": "start", "total": len(chunks), "source": source})

        summary = IngestSummary(source=source, total_chunks=len(chunks))

        logger.info("Embedding %d chunks …", len(chunks))
        embeddings = embed_chunks(chunks)

        for i, (chunk, embedding) in enumerate(zip(chunks, embeddings), 1):
            logger.info(
                "  [%d/%d] %s/%s#%s chunk=%d",
                i, len(chunks),
                chunk.source, chunk.collection, chunk.record_id, chunk.chunk_index,
            )
            cs = ChunkStats(
                source     = chunk.source,
                collection = chunk.collection,
                record_id  = chunk.record_id,
                entities   = 0,
                relations  = 0,
                merged     = 0,
            )

            try:
                entities, relations, merged = self._process_one(chunk, embedding)
                cs.entities  = len(entities)
                cs.relations = len(relations)
                cs.merged    = merged

                summary.ok_chunks       += 1
                summary.total_entities  += len(entities)
                summary.total_relations += len(relations)
                summary.total_merged    += merged

            except Exception as e:
                logger.exception("Chunk %s/%s failed: %s", chunk.collection, chunk.record_id, e)
                cs.error = str(e)
                summary.failed_chunks += 1

            summary.chunk_stats.append(cs)

            yield _sse({
                "t":               "progress",
                "current":         i,
                "total":           len(chunks),
                "collection":      chunk.collection,
                "record_id":       str(chunk.record_id),
                "entities":        cs.entities,
                "relations":       cs.relations,
                "merged":          cs.merged,
                "error":           cs.error,
                "total_entities":  summary.total_entities,
                "total_relations": summary.total_relations,
                "ok_chunks":       summary.ok_chunks,
                "failed_chunks":   summary.failed_chunks,
            })

        # Rebuild vector indexes
        yield _sse({"t": "reindex"})
        self._graph.create_indexes(rebuild=True)

        summary.elapsed_s = time.time() - t0
        logger.info("Ingest complete — %s", summary)

        yield _sse({
            "t":               "done",
            "source":          summary.source,
            "ok_chunks":       summary.ok_chunks,
            "failed_chunks":   summary.failed_chunks,
            "total_entities":  summary.total_entities,
            "total_relations": summary.total_relations,
            "total_merged":    summary.total_merged,
            "elapsed_s":       round(summary.elapsed_s, 1),
        })

    def run_all(self) -> dict[str, IngestSummary]:
        """
        Ingest all configured sources (postgres + mongo).

        Returns a dict keyed by source name.
        """
        results: dict[str, IngestSummary] = {}
        for source in ("postgres", "mongo"):
            try:
                results[source] = self.run(source)
            except Exception as e:
                logger.error("Source %s failed: %s", source, e)
                results[source] = IngestSummary(source=source, failed_chunks=-1)
        return results

    # ── core loop ─────────────────────────────────────────────────────────────

    def _process_chunks(
        self,
        chunks: list,
        source: str,
    ) -> IngestSummary:
        summary = IngestSummary(source=source, total_chunks=len(chunks))

        # Embed all chunk texts in one batched call
        logger.info("Embedding %d chunks …", len(chunks))
        embeddings = embed_chunks(chunks)

        for i, (chunk, embedding) in enumerate(zip(chunks, embeddings), 1):
            logger.info(
                "  [%d/%d] %s/%s#%s chunk=%d",
                i, len(chunks),
                chunk.source, chunk.collection, chunk.record_id, chunk.chunk_index,
            )
            cs = ChunkStats(
                source     = chunk.source,
                collection = chunk.collection,
                record_id  = chunk.record_id,
                entities   = 0,
                relations  = 0,
                merged     = 0,
            )

            try:
                entities, relations, merged = self._process_one(chunk, embedding)
                cs.entities  = len(entities)
                cs.relations = len(relations)
                cs.merged    = merged

                summary.ok_chunks       += 1
                summary.total_entities  += len(entities)
                summary.total_relations += len(relations)
                summary.total_merged    += merged

            except Exception as e:
                logger.exception("Chunk %s/%s failed: %s", chunk.collection, chunk.record_id, e)
                cs.error = str(e)
                summary.failed_chunks += 1

            summary.chunk_stats.append(cs)

        return summary

    def _process_one(
        self,
        chunk,
        embedding: list[float],
    ) -> tuple[list, list, int]:
        """
        Process one chunk through the full pipeline.

        Returns (entities, relations, merged_count).
        """
        # 1. Write chunk node + embedding
        chunk_id = self._graph.write_chunk(chunk, embedding)

        # 2. ML extraction (spaCy + GLiNER)
        spacy_result  = self._spacy.extract(chunk.text)
        gliner_result = self._gliner.extract(chunk.text, self._graph)

        # 3. Graph context (existing schema + similar entities)
        ctx = self._fetcher.fetch(spacy_result, gliner_result)

        # 4. LLM extraction → final entities + relations
        entities, relations = self._llm.extract(
            chunk.text, spacy_result, gliner_result, ctx,
        )

        if not entities:
            logger.debug("  No entities extracted from chunk %s", chunk.id)
            return [], [], 0

        # 5. Embed entity names (for future fuzzy-match / dedup)
        entity_names      = [e.name for e in entities]
        entity_embeddings = embed_texts(entity_names)
        for entity, emb in zip(entities, entity_embeddings):
            entity.embedding = emb

        # 6. Write entities + relations + mentions
        entity_ids = self._graph.write_entities(entities)
        self._graph.write_relations(relations)
        self._graph.write_mentions(chunk_id, entity_ids)

        # Count how many used merge_with_id (updated existing nodes)
        merged = sum(
            1 for e in entities
            if any(e.id == m.existing_id for m in ctx.entity_matches)
        )

        return entities, relations, merged


# ── source connection config ──────────────────────────────────────────────────

def _source_config(source: str) -> dict[str, Any]:
    """
    Build normaliser constructor kwargs from environment variables.
    These are the defaults — callers can override via normaliser_kwargs.
    """
    if source == "postgres":
        return {
            "host":     os.getenv("POSTGRES_HOST",     "localhost"),
            "port":     int(os.getenv("POSTGRES_PORT", "5432")),
            "dbname":   os.getenv("POSTGRES_DB",       "contracts"),
            "user":     os.getenv("POSTGRES_USER",     "lattice"),
            "password": os.getenv("POSTGRES_PASSWORD", "lattice123"),
        }
    if source == "mongo":
        return {
            "host":     os.getenv("MONGO_HOST",     "localhost"),
            "port":     int(os.getenv("MONGO_PORT", "27017")),
            "database": os.getenv("MONGO_DB",       "contracts_docs"),
        }
    raise ValueError(f"Unknown source {source!r}. Supported: postgres, mongo")
