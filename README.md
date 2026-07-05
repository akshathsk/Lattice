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

### Prerequisites
- **Docker Desktop** — must be running before step 1
- **OpenAI API key** — set in `backend/.env` (see below)
- **Node.js** — for the frontend

### 1. Environment variables

Create `backend/.env`:

```env
OPENAI_API_KEY=sk-...

FALKORDB_HOST=localhost
FALKORDB_PORT=6379

POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=contracts
POSTGRES_USER=lattice
POSTGRES_PASSWORD=lattice123

MONGO_HOST=localhost
MONGO_PORT=27017
MONGO_DB=contracts_docs
```

### 2. Start the databases

```bash
# Start FalkorDB, Postgres, and MongoDB containers
docker start falkordb lattice-postgres lattice-mongo

# First time only — bring them up from the compose file
# docker compose -f FalkorDB/build/docker/docker-compose.yml up -d
```

### 3. Start the backend

```bash
cd backend
/opt/homebrew/bin/uvicorn main:app --reload --port 8000
```

> The backend uses the Homebrew Python 3.13 install (which has all dependencies).
> Health check: http://localhost:8000/health

### 4. Start the frontend

```bash
cd frontend
npm install        # first time only
npm run dev        # → http://localhost:3000
```

### Build for production
```bash
cd frontend && npm run build   # outputs to frontend/dist/
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
