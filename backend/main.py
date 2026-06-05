"""
Lattice — FastAPI application.

Endpoints
---------
POST /chat                    Stream a GPT-4o answer grounded in graph context.
GET  /graph/schema            Current entity types + relation types.
GET  /graph/stats             Node and edge counts.
POST /graph/reindex           Rebuild HNSW vector indexes.
GET  /connectors/defaults     Connection defaults read from environment.
POST /connectors/{source}/test  Test a connector with optional config overrides.
POST /ingest/{source}         Trigger ingest (accepts connection overrides + auto-reindexes).
GET  /health                  Liveness check.

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
    allow_origins     = ["*"],
    allow_credentials = True,
    allow_methods     = ["*"],
    allow_headers     = ["*"],
)


# ── request / response models ─────────────────────────────────────────────────

class ChatRequest(BaseModel):
    query: str
    debug: bool = False


class ConnectorConfig(BaseModel):
    """
    Optional connection overrides for a data source.
    Any field left as None falls back to the environment variable default.
    """
    host:     str | None = None
    port:     int | None = None
    database: str | None = None   # mongo
    dbname:   str | None = None   # postgres
    user:     str | None = None
    password: str | None = None


class IngestRequest(BaseModel):
    tables:      list[str]     | None = None   # postgres — specific tables
    collections: list[str]     | None = None   # mongo — specific collections
    query:       str           | None = None   # optional source filter
    connection:  ConnectorConfig      = ConnectorConfig()


# ── helpers ───────────────────────────────────────────────────────────────────

def _env_defaults(source: str) -> dict:
    """Return the environment-variable defaults for a source."""
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
    raise ValueError(f"Unknown source {source!r}")


def _merge_config(source: str, cfg: ConnectorConfig) -> dict:
    """Merge env defaults with any non-None overrides from the request."""
    base     = _env_defaults(source)
    override = {k: v for k, v in cfg.model_dump().items() if v is not None}
    return {**base, **override}


# ── endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    ok = _graph().health_check()
    if not ok:
        raise HTTPException(status_code=503, detail="Graph DB not reachable")
    return {"status": "ok"}


@app.post("/chat")
def chat(req: ChatRequest):
    """Stream a GPT-4o answer grounded in knowledge-graph context.

    Normal mode  — yields raw text tokens.
    Debug mode   — yields SSE events (data: {...}\\n\\n) for each pipeline step,
                   then token events, then a done event.
    """
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="query must not be empty")

    import json as _json

    def _stream():
        try:
            for chunk in _chatbot().chat(req.query, debug=req.debug):
                yield chunk
        except Exception as e:
            logger.exception("Chat error: %s", e)
            if req.debug:
                yield f"data: {_json.dumps({'t': 'error', 'message': str(e)})}\n\n"
            else:
                yield f"\n\n[Error: {e}]"

    return StreamingResponse(_stream(), media_type="text/event-stream")


# ── graph ─────────────────────────────────────────────────────────────────────

@app.get("/graph/schema")
def graph_schema():
    return _graph().get_schema()


@app.get("/graph/stats")
def graph_stats():
    g = _graph()._graph
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


@app.post("/graph/reindex")
def reindex():
    """Rebuild HNSW vector indexes — call after bulk ingest."""
    _graph().create_indexes(rebuild=True)
    return {"status": "ok", "message": "Vector indexes rebuilt"}


@app.get("/graph/data")
def graph_data(limit: int = 300):
    """
    Return Entity nodes and their relationships for graph visualisation.

    Parameters
    ----------
    limit : Maximum number of Entity nodes to return (default 300).
            Edges are capped at 5 × limit.
    """
    g = _graph()._graph
    node_res = g.query(
        "MATCH (n:Entity) RETURN n.id, n.name, n.type LIMIT $limit",
        {"limit": limit},
    )
    edge_res = g.query(
        "MATCH (a:Entity)-[r]->(b:Entity) RETURN a.id, type(r), b.id LIMIT $elimit",
        {"elimit": limit * 5},
    )
    return {
        "nodes": [
            {"id": r[0], "name": r[1], "type": r[2]}
            for r in node_res.result_set
        ],
        "edges": [
            {"src": r[0], "type": r[1], "dst": r[2]}
            for r in edge_res.result_set
        ],
    }


# ── connectors ────────────────────────────────────────────────────────────────

@app.get("/connectors/defaults")
def connector_defaults():
    """
    Return the current connection defaults (from env vars) for each source.
    Passwords are omitted so the UI can pre-fill non-sensitive fields.
    """
    pg    = _env_defaults("postgres")
    mongo = _env_defaults("mongo")
    return {
        "postgres": {
            "host":     pg["host"],
            "port":     pg["port"],
            "database": pg["dbname"],
            "user":     pg["user"],
        },
        "mongo": {
            "host":     mongo["host"],
            "port":     mongo["port"],
            "database": mongo["database"],
        },
    }


@app.post("/connectors/{source}/test")
def test_connector(source: str, cfg: ConnectorConfig = ConnectorConfig()):
    """Test a connector with optional config overrides."""
    from normalise import get_normaliser

    if source not in ("postgres", "mongo"):
        raise HTTPException(status_code=400, detail=f"Unknown source {source!r}")

    merged = _merge_config(source, cfg)
    try:
        normaliser = get_normaliser(source, **merged)
        ok = normaliser.health_check()
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))

    if not ok:
        raise HTTPException(status_code=503, detail="Connection failed")
    return {"ok": True}


# ── ingest ────────────────────────────────────────────────────────────────────

@app.post("/ingest/{source}")
def ingest(source: str, req: IngestRequest = IngestRequest()):
    """
    Trigger ingest from a data source — streams SSE progress events.

    Events: start → progress (one per chunk) → reindex → done | error

    Accepts optional connection overrides — any field not supplied falls back
    to the environment variable default.
    """
    import json as _json
    from workflow.ingest import IngestPipeline

    if source not in ("postgres", "mongo"):
        raise HTTPException(status_code=400, detail=f"Unknown source {source!r}")

    normaliser_kwargs = _merge_config(source, req.connection)

    def _stream():
        try:
            pipeline = IngestPipeline(graph=_graph())
            yield from pipeline.stream_run(
                source,
                tables            = req.tables,
                collections       = req.collections,
                query             = req.query,
                normaliser_kwargs = normaliser_kwargs,
            )
        except Exception as e:
            logger.exception("Ingest error: %s", e)
            yield f"data: {_json.dumps({'t': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(_stream(), media_type="text/event-stream")
