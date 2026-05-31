# Lattice

An automated knowledge graph builder that ingests data from any source — structured or unstructured — extracts entities and relationships **without a predefined schema** using a hybrid ML + LLM pipeline, stores the result in a graph database, and exposes a chatbot interface to query it in natural language.

The graph schema emerges entirely from the data. No ontology is seeded at startup.

---

## How it works

```
Data Sources (Postgres · MongoDB · …)
        │
        ▼
[ Normalise ]              read + chunk source records → NormalisedChunk[]
        │
        ▼
[ Embed Chunks ]           sentence-transformers → 768-dim vector per chunk (batched)
        │
        ├─ write_chunk()   Chunk node + embedding → FalkorDB
        │
        ▼
[ Stage 1 — ML Extraction ]
    spaCy                  NER + subject-verb-object dependency parse
    GLiNER                 zero-shot NER using live graph schema as label hints
        │                  (skipped on first chunk — schema starts empty)
        ▼
[ Graph Context ]          query FalkorDB: existing entity/relation types + KNN matches
        │                  → prevents duplicate nodes, keeps schema consistent
        ▼
[ Stage 2 — LLM Extraction ]
    GPT-4o (structured)    resolves entities, types relations, decides merges
        │
        ├─ embed entities  768-dim vector per entity name
        ├─ write_entities  Entity nodes → FalkorDB (MERGE on stable id)
        ├─ write_relations edges → FalkorDB (MERGE)
        └─ write_mentions  (:Chunk)-[:MENTIONS]->(:Entity)
```

### Why two extraction stages?

| What | Who | Why |
|---|---|---|
| Span detection | GLiNER | Fast, cheap, catches entities at high throughput |
| Dependency triples | spaCy | Free grammatical relation signal |
| Graph awareness | FalkorDB query | Consistency with existing schema; enables incremental re-ingest |
| Disambiguation & relation typing | GPT-4o | High-accuracy judgement; deduplicates against existing nodes |

LLM calls are expensive. Running ML first and fetching graph context means GPT-4o receives pre-structured, shorter prompts with higher accuracy per chunk.

---

## What's implemented

### Infrastructure
- **`backend/startup.py`** — starts FalkorDB, Postgres, and MongoDB Docker containers, seeds demo data, creates vector indexes. Schema is **not** seeded — it grows entirely from extraction output.

### Connectors & demo data
- **`backend/connectors/postgres/seed.sql`** — legal & contract demo data: 6 tables (parties, contracts, contract_parties, clauses, obligations, regulations), ~40 rows total
- **`backend/connectors/mongo/seed.py`** — unstructured contract documents: 5 collections (emails, memos, notes, amendments, compliance), ~13 documents

### Normalise layer (`backend/normalise/`)
Reads source databases and outputs a flat list of `NormalisedChunk` objects — the universal representation passed to every downstream stage.

| Module | Purpose |
|---|---|
| `models.py` | `NormalisedChunk(id, source, database, collection, record_id, chunk_index, text, metadata)` |
| `postgres.py` | `PostgresNormaliser` — auto-discovers all tables via `information_schema`; renders each row as labelled key-value text |
| `mongo.py` | `MongoNormaliser` — auto-discovers all collections; renders each document with body fields last |
| `base.py` | `BaseNormaliser` ABC with `normalise()`, `health_check()` |
| `chunker.py` | Text chunking with configurable size and overlap |
| `__init__.py` | `get_normaliser("postgres" | "mongo", **cfg)` factory |

Both normalisers are generic — they work on any Postgres/MongoDB database regardless of the schema.

### Graph DB plugin layer (`backend/graph/`)
Swappable graph database backends behind a common interface. The active plugin is selected by the `GRAPH_DB_PLUGIN` env var (default: `falkordb`).

| Module | Purpose |
|---|---|
| `base.py` | `GraphDBPlugin` ABC — 10 methods: `write_chunk`, `write_entities`, `write_relations`, `write_mentions`, `get_schema`, `fuzzy_match_entities`, `vector_search`, `traverse`, `create_indexes`, `health_check` |
| `falkordb.py` | **Fully implemented** FalkorDB plugin — HNSW vector index (cosine, 768-dim), KNN via `db.idx.vector.queryNodes`, schema tracked in Redis sets, openCypher MERGE for idempotent writes |
| `models.py` | `Entity(id, name, type, embedding, properties)` with stable `sha256` ID from type+name · `Relation(source_id, target_id, type)` |
| `__init__.py` | `get_graph_plugin("falkordb", **cfg)` factory |

### Extraction pipeline (`backend/extraction/`)

| Module | Purpose |
|---|---|
| `embedder.py` | `embed_text()` / `embed_texts()` / `embed_chunks()` — `sentence-transformers/all-mpnet-base-v2`, 768-dim, MPS-accelerated, batched |
| `models.py` | `SpacyResult`, `SpacyEntity`, `SpacyRelation`, `GlinerResult`, `GlinerEntity` with `to_prompt_dict()` |
| `spacy_extractor.py` | `SpacyExtractor(en_core_web_lg)` — NER with type normalisation (ORG→Organization, PERSON→Person, GPE→Location, LAW→Regulation, …) + SVO extraction from dependency parse |
| `gliner_extractor.py` | `GlinerExtractor(urchade/gliner_medium-v2.1)` — zero-shot NER using live graph schema labels as hints; returns `skipped=True` when schema is empty (first chunk bootstrap) |
| `graph_context.py` | `GraphContextFetcher` — embeds each ML candidate, runs KNN fuzzy match against existing Entity nodes, fetches 1-hop neighbourhood edges; returns `GraphContext` for the LLM prompt |
| `llm_extractor.py` | `LLMExtractor` — GPT-4o structured output (`_LLMOutput` pydantic schema, strict mode); `merge_with_id` signals the LLM to reuse an existing node rather than create a duplicate |

### Ingest pipeline (`backend/workflow/`)

| Module | Purpose |
|---|---|
| `ingest.py` | `IngestPipeline` — wires all stages end-to-end. `run(source)` ingests one source; `run_all()` runs postgres + mongo. `IngestSummary` tracks chunk counts, entity/relation totals, merge counts, and per-chunk errors. |

### Verified results (legal demo data)

After running `pipeline.run_all()` against live containers:

| | Postgres | MongoDB |
|---|---|---|
| Chunks | 52 / 52 ok | 14 / 14 ok |
| Entities extracted | 263 | 271 |
| Entities merged (deduped) | 99 | 107 |
| Relations | 134 | 144 |
| Time | 111 s | 113 s |

**FalkorDB state after full ingest:** 311 Entity nodes · 74 Chunk nodes · 23 entity labels · 37 relation types — all emerged from extraction, none seeded.

---

## What's pending

### Immediate next step — RAG query layer + API

| Task | Details |
|---|---|
| `backend/chat/vector_retriever.py` | Embed query → KNN on Chunk.embedding → top-K chunks |
| `backend/chat/graph_retriever.py` | GLiNER on query → entity lookup → N-hop traversal from anchors |
| `backend/chat/merger.py` | Deduplicate + rank chunks from both paths |
| `backend/chat/chatbot.py` | GPT-4o (or Claude) chatbot with streamed responses + source citations |
| `backend/main.py` | FastAPI app: `POST /ingest`, `GET /graph/nodes`, `GET /graph/edges`, `POST /chat` |

### More connectors

| Connector | Details |
|---|---|
| Filesystem | PDF, Word (.docx), plain text, Markdown via `unstructured` |
| Web / URL | Crawl + extract; sitemap support |
| CSV / Excel | Structured rows → chunks via `pandas` |
| JSON / XML | Generic document connectors |
| REST API | Configurable auth, pagination |

### Frontend

Next.js 14 app:
- Streaming chat UI (Vercel AI SDK)
- Interactive graph visualisation (`react-force-graph` or `Neovis.js`)
- Source manager (upload files, add URLs, configure DB connections)

### Additional graph DB plugins

| Plugin | Status |
|---|---|
| Neo4j | Planned — mature ecosystem, AuraDB managed option |
| Memgraph | Planned — in-memory, real-time streaming |
| Kuzu | Planned — embeddable, no server |

### Polish

- Incremental re-ingest (graph diff — only update changed records)
- Confidence scoring on extracted triples
- Entity deduplication tuning (cosine threshold configurable)
- Export graph as JSON-LD / RDF Turtle
- Docker Compose (single `docker compose up` for everything)

---

## Project structure

```
knowledge-graph-lattice/
├── backend/
│   ├── startup.py                  ← start containers, seed data, create indexes
│   ├── connectors/
│   │   ├── postgres/seed.sql       ← legal demo data (6 tables)
│   │   └── mongo/seed.py           ← contract documents (5 collections)
│   ├── normalise/
│   │   ├── models.py               ← NormalisedChunk
│   │   ├── postgres.py             ← PostgresNormaliser
│   │   ├── mongo.py                ← MongoNormaliser
│   │   └── base.py + chunker.py
│   ├── graph/
│   │   ├── base.py                 ← GraphDBPlugin ABC
│   │   ├── falkordb.py             ← FalkorDB plugin ✓
│   │   └── models.py               ← Entity, Relation
│   ├── extraction/
│   │   ├── embedder.py             ← sentence-transformers ✓
│   │   ├── spacy_extractor.py      ← NER + SVO ✓
│   │   ├── gliner_extractor.py     ← zero-shot NER ✓
│   │   ├── graph_context.py        ← KNN + neighbourhood fetch ✓
│   │   └── llm_extractor.py        ← GPT-4o structured output ✓
│   └── workflow/
│       └── ingest.py               ← IngestPipeline ✓
│
│   (pending)
│   ├── chat/                       ← RAG query layer
│   └── main.py                     ← FastAPI app
│
└── frontend/                       ← Next.js app (not started)
```

---

## Tech stack

| Layer | Choice |
|---|---|
| Graph DB | FalkorDB (Redis module, GraphBLAS, HNSW, openCypher) |
| LLM extraction | OpenAI GPT-4o (structured outputs) |
| ML NER | GLiNER `urchade/gliner_medium-v2.1` |
| NLP pipeline | spaCy `en_core_web_lg` |
| Embeddings | `sentence-transformers/all-mpnet-base-v2` (768-dim, local, MPS) |
| Data sources | PostgreSQL · MongoDB |
| Backend | Python 3.13 · FastAPI (pending) |
| Frontend | Next.js 14 (pending) |

---

## Quickstart

```bash
# 1. Start containers + seed demo data
cd backend
python startup.py

# 2. Configure environment
cp .env.example .env
# Set OPENAI_API_KEY in .env

# 3. Run full ingest
PYTHONPATH=. python - <<'EOF'
from workflow.ingest import IngestPipeline
pipeline = IngestPipeline()
results = pipeline.run_all()
for source, summary in results.items():
    print(summary)
EOF
```
