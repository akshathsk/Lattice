# Lattice

An automated knowledge graph builder that ingests data from any source — structured or unstructured — extracts entities and relationships without a predefined schema using a hybrid ML + LLM pipeline, stores the result in a graph database, and exposes a chatbot interface to query it in natural language.

```
Data Sources (Postgres · MongoDB · …)
        │
        ▼
   Normalise                 chunk + convert to text       ✓
        │
        ▼
   Embed Chunks              768-dim vectors (mpnet)       ✓
        │
        ▼
   ML Extraction             spaCy NER + GLiNER            ✓
        │
        ▼
   Graph Context             KNN match existing nodes      ✓
        │
        ▼
   LLM Extraction            GPT-4o structured output      ✓
        │
        ▼
   FalkorDB                  entities + relations + HNSW   ✓
        │
        ▼
   RAG Query Layer           vector + graph retrieval      ✓
        │
        ▼
   Chatbot API               FastAPI streaming + debug     ✓
        │
        ▼
   Frontend                  chat · graph · connectors UI  ✓
```

The graph schema emerges from the data — nothing is seeded at startup.

## Run

```bash
# 1. Start FalkorDB + Postgres + Mongo
docker compose up -d   # or start the existing containers

# 2. Start the API
cd backend && python3 -m uvicorn main:app --reload

# 3. Open the UI
open frontend/index.html
```

## API

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/chat` | Stream a GPT-4o answer (`debug: true` for step trace) |
| `POST` | `/ingest/{source}` | Ingest from `postgres` or `mongo` (streams progress) |
| `GET` | `/graph/data` | Entity nodes + edges for visualisation |
| `GET` | `/graph/schema` | Known entity types + relation types |
| `GET` | `/graph/stats` | Node and edge counts |
| `POST` | `/graph/reindex` | Rebuild HNSW vector indexes |
| `GET` | `/connectors/defaults` | Connection defaults from env vars |
| `POST` | `/connectors/{source}/test` | Test a connector |
| `GET` | `/health` | Liveness check |
