"""
Lattice — FastAPI application.

Endpoints
---------
POST /chat                          Stream a GPT-4o answer grounded in graph context.
GET  /graph/data                    Entity nodes + edges for visualisation.
GET  /graph/schema                  Current entity types + relation types.
GET  /graph/stats                   Node and edge counts.
POST /graph/reindex                 Rebuild HNSW vector indexes.
GET  /connectors/defaults           Connection defaults from environment.
POST /connectors/{source}/test      Test postgres | mongo | mysql | elasticsearch.
POST /connectors/rest/test          Test a REST API endpoint.
POST /connectors/s3/test            Test an S3 bucket.
POST /ingest/{source}               Ingest from postgres | mongo | mysql | elasticsearch.
POST /ingest/file                   Ingest uploaded files (multipart).
POST /ingest/rest                   Ingest from a REST API endpoint.
POST /ingest/s3                     Ingest from an S3 bucket.
GET  /health                        Liveness check.

Run
---
    cd backend
    uvicorn main:app --reload
"""

from __future__ import annotations

import logging
import os
import shutil
import tempfile
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
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
    version     = "0.2.0",
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
    """Optional connection overrides — any field left as None falls back to env defaults."""
    host:     str | None = None
    port:     int | None = None
    database: str | None = None   # mongo / elasticsearch index
    dbname:   str | None = None   # postgres / mysql
    user:     str | None = None
    password: str | None = None


class IngestRequest(BaseModel):
    tables:      list[str]      | None = None
    collections: list[str]      | None = None
    query:       str            | None = None
    connection:  ConnectorConfig       = ConnectorConfig()


class RestTestRequest(BaseModel):
    url:         str
    method:      str        = "GET"
    auth_header: str | None = None


class RestIngestRequest(BaseModel):
    url:         str
    method:      str        = "GET"
    auth_header: str | None = None
    json_path:   str | None = None


class S3TestRequest(BaseModel):
    bucket:     str
    region:     str        = "us-east-1"
    access_key: str | None = None
    secret_key: str | None = None


class S3IngestRequest(BaseModel):
    bucket:     str
    prefix:     str        = ""
    region:     str        = "us-east-1"
    access_key: str | None = None
    secret_key: str | None = None


# ── connection helpers ────────────────────────────────────────────────────────

_DB_SOURCES = ("postgres", "mongo", "mysql", "elasticsearch")


def _env_defaults(source: str) -> dict:
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
    if source == "mysql":
        return {
            "host":     os.getenv("MYSQL_HOST",     "localhost"),
            "port":     int(os.getenv("MYSQL_PORT", "3306")),
            "dbname":   os.getenv("MYSQL_DB",       ""),
            "user":     os.getenv("MYSQL_USER",     ""),
            "password": os.getenv("MYSQL_PASSWORD", ""),
        }
    if source == "elasticsearch":
        return {
            "host":     os.getenv("ES_HOST",     "localhost"),
            "port":     int(os.getenv("ES_PORT", "9200")),
            "user":     os.getenv("ES_USER",     ""),
            "password": os.getenv("ES_PASSWORD", ""),
            "index":    os.getenv("ES_INDEX",    ""),
        }
    raise ValueError(f"Unknown source {source!r}")


def _merge_config(source: str, cfg: ConnectorConfig) -> dict:
    """Merge env defaults with non-None overrides from the request."""
    base     = _env_defaults(source)
    override = {k: v for k, v in cfg.model_dump().items() if v is not None}
    merged   = {**base, **override}
    # elasticsearch: ConnectorConfig.database → normaliser kwarg 'index'
    if source == "elasticsearch" and "database" in merged:
        merged["index"] = merged.pop("database")
    return merged


# ── endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    ok = _graph().health_check()
    if not ok:
        raise HTTPException(status_code=503, detail="Graph DB not reachable")
    return {"status": "ok"}


@app.post("/chat")
def chat(req: ChatRequest):
    """Stream a GPT-4o answer.  debug=true adds pipeline step events."""
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
    _graph().create_indexes(rebuild=True)
    return {"status": "ok", "message": "Vector indexes rebuilt"}


@app.get("/graph/data")
def graph_data(limit: int = 300):
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
        "nodes": [{"id": r[0], "name": r[1], "type": r[2]} for r in node_res.result_set],
        "edges": [{"src": r[0], "type": r[1], "dst": r[2]} for r in edge_res.result_set],
    }


# ── connectors ────────────────────────────────────────────────────────────────

@app.get("/connectors/defaults")
def connector_defaults():
    """Return non-sensitive connection defaults for the UI to pre-fill."""
    pg    = _env_defaults("postgres")
    mongo = _env_defaults("mongo")
    return {
        "postgres": {"host": pg["host"], "port": pg["port"], "database": pg["dbname"], "user": pg["user"]},
        "mongo":    {"host": mongo["host"], "port": mongo["port"], "database": mongo["database"]},
    }


@app.post("/connectors/rest/test")
def test_rest_connector(req: RestTestRequest):
    """Test a REST API endpoint is reachable."""
    from normalise.rest_api import RestApiNormaliser
    try:
        n  = RestApiNormaliser(url=req.url, method=req.method, auth_header=req.auth_header)
        ok = n.health_check()
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))
    if not ok:
        raise HTTPException(status_code=503, detail="Endpoint not reachable or returned 5xx")
    return {"ok": True}


@app.post("/connectors/s3/test")
def test_s3_connector(req: S3TestRequest):
    """Test S3 bucket access."""
    from normalise.s3 import S3Normaliser
    try:
        n  = S3Normaliser(bucket=req.bucket, region=req.region,
                          access_key=req.access_key, secret_key=req.secret_key)
        ok = n.health_check()
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))
    if not ok:
        raise HTTPException(status_code=503, detail="Bucket not accessible")
    return {"ok": True}


@app.post("/connectors/{source}/test")
def test_connector(source: str, cfg: ConnectorConfig = ConnectorConfig()):
    """Test a database connector (postgres | mongo | mysql | elasticsearch)."""
    from normalise import get_normaliser

    if source not in _DB_SOURCES:
        raise HTTPException(status_code=400, detail=f"Unknown source {source!r}")

    merged = _merge_config(source, cfg)
    try:
        normaliser = get_normaliser(source, **merged)
        ok         = normaliser.health_check()
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))

    if not ok:
        raise HTTPException(status_code=503, detail="Connection failed")
    return {"ok": True}


# ── ingest ────────────────────────────────────────────────────────────────────

@app.post("/ingest/file")
async def ingest_file(files: list[UploadFile] = File(...)):
    """
    Ingest uploaded documents — streams SSE progress events.
    Accepted: .txt .md .pdf .docx .csv .json
    """
    import json as _json
    from normalise.file  import FileNormaliser
    from workflow.ingest import IngestPipeline

    if not files:
        raise HTTPException(status_code=400, detail="No files provided")

    tmp_dir = Path(tempfile.mkdtemp(prefix="lattice_upload_"))
    saved: list[str] = []
    for f in files:
        dest = tmp_dir / (f.filename or "upload")
        with open(dest, "wb") as fh:
            shutil.copyfileobj(f.file, fh)
        saved.append(str(dest))

    def _stream():
        try:
            normaliser = FileNormaliser(file_paths=saved)
            pipeline   = IngestPipeline(graph=_graph())
            yield from pipeline.stream_run_normaliser(normaliser, source="file")
        except Exception as e:
            logger.exception("File ingest error: %s", e)
            yield f"data: {_json.dumps({'t': 'error', 'message': str(e)})}\n\n"
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    return StreamingResponse(_stream(), media_type="text/event-stream")


@app.post("/ingest/rest")
def ingest_rest(req: RestIngestRequest):
    """Ingest from a REST API endpoint — streams SSE progress events."""
    import json as _json
    from normalise.rest_api import RestApiNormaliser
    from workflow.ingest    import IngestPipeline

    def _stream():
        try:
            normaliser = RestApiNormaliser(
                url=req.url, method=req.method,
                auth_header=req.auth_header, json_path=req.json_path,
            )
            pipeline = IngestPipeline(graph=_graph())
            yield from pipeline.stream_run_normaliser(normaliser, source="rest")
        except Exception as e:
            logger.exception("REST ingest error: %s", e)
            yield f"data: {_json.dumps({'t': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(_stream(), media_type="text/event-stream")


@app.post("/ingest/s3")
def ingest_s3(req: S3IngestRequest):
    """Ingest from an S3 bucket — streams SSE progress events."""
    import json as _json
    from normalise.s3    import S3Normaliser
    from workflow.ingest import IngestPipeline

    def _stream():
        try:
            normaliser = S3Normaliser(
                bucket=req.bucket, prefix=req.prefix,
                region=req.region, access_key=req.access_key, secret_key=req.secret_key,
            )
            pipeline = IngestPipeline(graph=_graph())
            yield from pipeline.stream_run_normaliser(normaliser, source="s3")
        except Exception as e:
            logger.exception("S3 ingest error: %s", e)
            yield f"data: {_json.dumps({'t': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(_stream(), media_type="text/event-stream")


@app.post("/ingest/{source}")
def ingest(source: str, req: IngestRequest = IngestRequest()):
    """
    Ingest from a database source — streams SSE progress events.
    Supported: postgres | mongo | mysql | elasticsearch
    """
    import json as _json
    from workflow.ingest import IngestPipeline

    if source not in _DB_SOURCES:
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
