"""
Lattice — FastAPI application.

Endpoints
---------
POST /chat              Stream a GPT-4o answer grounded in graph context.
GET  /graph/schema      Current entity types + relation types in the graph.
GET  /graph/stats       Node and edge counts.
POST /ingest/{source}   Trigger ingest from a named source (postgres | mongo).
GET  /health            Liveness check.

Run
---
    cd backend
    uvicorn main:app --reload
"""

from __future__ import annotations

import logging
import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

# ── env ───────────────────────────────────────────────────────────────────────
_env = Path(__file__).parent / ".env"
if _env.exists():
    load_dotenv(_env)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s — %(message)s")
logger = logging.getLogger(__name__)

# ── lazy singletons ───────────────────────────────────────────────────────────
# Loaded once on first request — avoids loading heavy ML models at import time.

@lru_cache(maxsize=1)
def _graph():
    from graph import get_graph_plugin
    return get_graph_plugin()

@lru_cache(maxsize=1)
def _chatbot():
    from chat.retriever import Retriever
    from chat.chatbot   import Chatbot
    return Chatbot(Retriever(_graph()))


# ── app ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title       = "Lattice API",
    description = "Knowledge-graph RAG API",
    version     = "0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins     = ["*"],   # tighten for production
    allow_credentials = True,
    allow_methods     = ["*"],
    allow_headers     = ["*"],
)


# ── request / response models ─────────────────────────────────────────────────

class ChatRequest(BaseModel):
    query: str

class IngestRequest(BaseModel):
    tables:      list[str] | None = None   # postgres only
    collections: list[str] | None = None   # mongo only
    query:       str       | None = None   # optional filter


# ── endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    ok = _graph().health_check()
    if not ok:
        raise HTTPException(status_code=503, detail="Graph DB not reachable")
    return {"status": "ok"}


@app.post("/chat")
def chat(req: ChatRequest):
    """
    Stream a GPT-4o answer grounded in knowledge-graph context.

    Returns a text/event-stream where each event is a token delta.
    """
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="query must not be empty")

    def _stream():
        try:
            for token in _chatbot().chat(req.query):
                yield token
        except Exception as e:
            logger.exception("Chat error: %s", e)
            yield f"\n\n[Error: {e}]"

    return StreamingResponse(_stream(), media_type="text/event-stream")


@app.get("/graph/schema")
def graph_schema():
    """Return all entity types and relation types currently in the graph."""
    return _graph().get_schema()


@app.post("/graph/reindex")
def reindex():
    """
    Rebuild vector indexes from scratch.

    FalkorDB's HNSW index does not always auto-update when embeddings are
    added to existing nodes via MERGE+SET.  Call this endpoint after a bulk
    ingest to ensure all Chunk and Entity embeddings are fully indexed.
    """
    _graph().create_indexes(rebuild=True)
    return {"status": "ok", "message": "Vector indexes rebuilt"}


@app.get("/graph/stats")
def graph_stats():
    """Return node and edge counts by label/type."""
    g = _graph()._graph   # direct FalkorDB graph handle

    node_res = g.query(
        "MATCH (n) RETURN labels(n)[0] AS label, count(n) AS cnt ORDER BY cnt DESC"
    )
    edge_res = g.query(
        "MATCH ()-[r]->() RETURN type(r) AS t, count(r) AS cnt ORDER BY cnt DESC"
    )

    return {
        "nodes": [{"label": r[0], "count": r[1]} for r in node_res.result_set],
        "edges": [{"type":  r[0], "count": r[1]} for r in edge_res.result_set],
    }


@app.post("/ingest/{source}")
def ingest(source: str, req: IngestRequest = IngestRequest()):
    """
    Trigger ingest from a data source.

    source : ``postgres`` or ``mongo``

    The ingest runs synchronously — for large datasets wire this to a
    background task queue (Celery / ARQ) and return a job ID instead.
    """
    from workflow.ingest import IngestPipeline

    if source not in ("postgres", "mongo"):
        raise HTTPException(status_code=400, detail=f"Unknown source {source!r}")

    try:
        pipeline = IngestPipeline(graph=_graph())
        summary  = pipeline.run(
            source,
            tables      = req.tables,
            collections = req.collections,
            query       = req.query,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    return {
        "source":          summary.source,
        "ok_chunks":       summary.ok_chunks,
        "failed_chunks":   summary.failed_chunks,
        "total_entities":  summary.total_entities,
        "total_relations": summary.total_relations,
        "total_merged":    summary.total_merged,
        "elapsed_s":       round(summary.elapsed_s, 1),
    }
