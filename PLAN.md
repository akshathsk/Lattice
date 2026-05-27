# Knowledge Graph Lattice — Build Plan

## Vision

An automated knowledge graph builder that ingests data from any source (structured or unstructured), extracts entities and relationships without a predefined schema using a hybrid ML + LLM pipeline, stores the result in a graph database, and exposes a chatbot interface to query it in natural language.

The system makes no assumptions about the shape or domain of the data. The graph schema emerges from the data itself.

---

## Core Architecture

```
Data Sources
    │
    ▼
[ Connectors ]               ← pluggable, one per source type
    │
    ▼
[ Ingestion & Chunking ]     ← normalize everything to text/structured chunks
    │
    ├──────────────────────────────┬──────────────────────────────────┐
    │  raw chunk text              │  raw chunk text                  │  raw chunk text
    ▼                              ▼                                  │
[ Embed Chunk ]            [ Stage 1: ML Extraction ]                │
  sentence-transformers       GLiNER  → entity spans + types         │
  → chunk.embedding           spaCy   → dependency triples, coref    │
    │                              │                                  │
    │  vector                      │  ML outputs                      │
    │                              ▼                                  │
    │                    [ Graph Context Fetch ]                      │
    │                      Graph DB Plugin → existing labels,         │
    │                      rel types, top-N fuzzy entity matches      │
    │                              │                                  │
    │                              │  graph context                   │
    │                              └──────────────┬────────────────────┘
    │                                             │  raw chunk + ML outputs + graph context
    │                                             ▼
    │                                 [ Stage 2: Claude LLM Extraction ]
    │                                   resolves entities, types relations,
    │                                   decides merges with existing nodes
    │                                             │
    │              ┌──────────────────────────────┘
    ▼              ▼
[ Graph DB Plugin ]          ← swappable backend (config-driven)
  FalkorDBPlugin  ← default, ships first
  Neo4jPlugin     ← future
  MemgraphPlugin  ← future
  KuzuPlugin      ← future
                   │
                   ▼
[ Graph Store ]
  (:Chunk {embedding})  ← vector index (native to each plugin's DB)
  (:Entity)
  (:Chunk)-[:MENTIONS]->(:Entity)   ← chunk linked to every entity it produced
  (:Entity)-[:RELATION]->(:Entity)
                   │
                   ▼
[ Vector-Graph RAG Query Layer ]
  1. embed query → vector search on Chunk nodes → top-K chunks
  2. follow :MENTIONS edges → anchor entities
  3. N-hop graph traversal from anchors → subgraph context
  4. merge vector hits + graph context → Claude
                   │
                   ▼
         [ Chatbot (Claude) ]
                   │
                   ▼
           [ Web UI / API ]
```

---

## Tech Stack

### Backend
| Layer | Choice | Reason |
|---|---|---|
| Language | Python 3.12+ | Best ecosystem for NLP, graph, and LLM tooling |
| API server | FastAPI | Async, typed, OpenAPI docs out of the box |
| LLM | Claude (claude-sonnet-4-6) | Relation extraction, entity disambiguation, graph-aware merging |
| NER (zero-shot) | GLiNER | Fast local entity detection with no predefined type list; no API cost |
| NLP pipeline | spaCy | Dependency parsing, coreference, POS — feeds structured hints to GLiNER and Claude |
| Embeddings | `sentence-transformers` (local) | Chunk vectorisation + entity dedup; stored directly in the graph DB via its native vector index — no separate vector DB needed |
| Graph DB | Plugin-based (FalkorDB default) | Swappable backend; FalkorDB ships first — Redis-backed, GraphBLAS traversal, native HNSW vector index, openCypher |
| Pipeline orchestration | Custom (simple queue) → Prefect later | Start simple, add scheduling when needed |
| Document parsing | `unstructured` (open source) | Single library handles PDF, Word, HTML, images, email, etc. |
| Structured data | `pandas` + `sqlalchemy` | CSV, Excel, JSON, SQL databases |

### Frontend / UI
| Layer | Choice | Reason |
|---|---|---|
| UI framework | Next.js 14 (App Router) | Fast to build, easy to deploy, server components |
| Graph visualization | `react-force-graph` or `Neovis.js` | Interactive graph rendering in browser |
| Chat UI | Custom with Vercel AI SDK | Streaming responses, tool call rendering |
| Styling | Tailwind CSS | |

### Infrastructure
| Layer | Choice | Reason |
|---|---|---|
| Local dev | Docker Compose | FalkorDB + API + UI in one command |
| Secrets | `.env` files | Simple for now |

---

## Graph Database Plugins (Pluggable)

Each graph DB plugin implements a common `GraphDBPlugin` abstract interface. Swapping the database requires only a config change — no changes to the extraction pipeline, chatbot, or API layer.

### Plugin Interface

Every plugin must implement these operations:

| Method | Purpose |
|---|---|
| `write_chunk(chunk, embedding)` | Store a chunk node with its vector |
| `write_entities(entities)` | Upsert entity nodes (merge by id) |
| `write_relations(triples)` | Write typed edges between entities |
| `write_mentions(chunk_id, entity_ids)` | Link chunk → entities it produced |
| `get_schema()` | Return existing entity types + relation types (for graph context fetch) |
| `fuzzy_match_entities(names)` | Find existing nodes that may match candidate names |
| `vector_search(embedding, k)` | KNN search on chunk embeddings → top-K chunks |
| `traverse(entity_ids, hops)` | N-hop graph traversal from anchor entities |
| `create_indexes()` | Create vector + range indexes on startup |
| `health_check()` | Verify connection is live |

The plugin is selected via `GRAPH_DB_PLUGIN` env var (default: `falkordb`).

### Available Plugins

| Plugin | Status | DB | Notes |
|---|---|---|---|
| `falkordb` | **Ships first** | FalkorDB (Redis module) | GraphBLAS traversal, native HNSW, openCypher, Bolt protocol |
| `neo4j` | Future | Neo4j 5 | Mature ecosystem, disk-based, AuraDB managed option |
| `memgraph` | Future | Memgraph | In-memory, real-time streaming, openCypher |
| `kuzu` | Future | Kuzu | Embeddable, no server, analytical queries |

### FalkorDB Plugin (default)

- Connects via the `falkordb` Python client (or `neo4j` driver over Bolt)
- Vector index: `CREATE VECTOR INDEX FOR (c:Chunk) ON (c.embedding)` with HNSW cosine
- KNN query: `CALL db.idx.vector.queryNodes('Chunk', 'embedding', $k, vecf32($vec))`
- Schema introspection: maintained in a Redis hash (`HSET lattice:schema labels ...`) updated on every write, since FalkorDB doesn't expose `db.labels()` as a procedure
- Source: [`FalkorDB/`](./FalkorDB/) submodule (fork: [akshathsk/FalkorDB-lattice](https://github.com/akshathsk/FalkorDB-lattice))

---

## Data Connectors (Pluggable)

Each connector implements a common interface: given a source config, it yields normalized `Document` objects.

### Planned Connectors
- **File system** — PDF, Word (.docx), PowerPoint, Excel, CSV, JSON, XML, plain text, Markdown
- **Web / URL** — crawl a URL or sitemap, extract text
- **Database** — connect via SQLAlchemy (Postgres, MySQL, SQLite); introspect schema + dump rows
- **API** — generic REST/JSON endpoint with configurable auth
- **Google Drive** — via MCP or OAuth connector
- **Code repositories** — parse source files, docstrings, README
- **Email** — Gmail via MCP (already available in this environment)

---

## Extraction Engine — Hybrid ML + LLM Pipeline

This is the core of the system. Extraction runs in two stages per chunk, with a graph context fetch in between.

### Stage 1 — ML Extraction (fast, local, no cost)

**GLiNER** runs zero-shot NER over the chunk. Unlike spaCy's fixed label set, GLiNER accepts arbitrary label hints at inference time — useful once the graph has established types like `Drug`, `Legal Clause`, or `Database Table`. On the first ingest (empty graph) it runs with generic labels.

**spaCy** runs concurrently to extract:
- Dependency parse (subject-verb-object structure → candidate relation triples)
- Coreference clusters ("he", "it", "the company" → resolved to named entities)
- Sentences boundaries (used to scope relation candidates)

Output: a list of candidate entities with spans + candidate (subject, verb, object) triples from syntax.

### Graph Context Fetch — Query Neo4j Before Writing

Before calling Claude, query the existing graph for:

```cypher
// 1. What entity types already exist?
CALL db.labels() YIELD label RETURN label

// 2. What relation types already exist?
CALL db.relationshipTypes() YIELD relationshipType RETURN relationshipType

// 3. Do any existing entities fuzzy-match the candidates found by GLiNER?
MATCH (e:Entity)
WHERE e.name IN $candidate_names OR e.name =~ $fuzzy_patterns
RETURN e.id, e.name, e.type, e.description LIMIT 20
```

This context is passed to Claude alongside the chunk. The LLM now knows the graph's current vocabulary — it can reuse existing types instead of inventing synonyms, and can identify that "Sam Altman" in this chunk is the same node already in the graph.

### Stage 2 — LLM Extraction (Claude)

Claude receives the same raw chunk text that was given to GLiNER and spaCy, plus their outputs, plus graph context — so it can validate, correct, and extend what the ML models found rather than working from a lossy summary.

- **Raw chunk text** (identical input to Stage 1 — Claude sees the source, not just the ML parse)
- GLiNER-detected entity spans with confidence scores
- spaCy dependency triples and resolved coreference clusters
- Existing graph entity types and relation types
- Top-N fuzzy-matching existing entities from Neo4j

Claude outputs structured JSON:
```json
{
  "entities": [
    {"name": "OpenAI", "type": "Organization", "merge_with_id": "ent_042", "description": "..."},
    {"name": "Sam Altman", "type": "Person", "merge_with_id": null, "description": "..."}
  ],
  "triples": [
    {"head": "Sam Altman", "relation": "founded_by_inverse", "tail": "OpenAI", "confidence": 0.9},
    {"head": "Sam Altman", "relation": "role", "tail": "CEO", "confidence": 0.85}
  ]
}
```

The `merge_with_id` field is how the LLM signals "this entity is the same as an existing graph node." This drives deduplication without a separate pass.

### Why this layering?

| What | Who does it | Why |
|---|---|---|
| Span detection | GLiNER | Fast, cheap, catches entities the LLM might miss at high throughput |
| Syntax structure | spaCy | Grammatical relation candidates — free signal |
| Graph awareness | Neo4j query | Consistency with existing schema; enables incremental ingestion |
| Disambiguation & relation typing | Claude | High-accuracy judgement call; has full context |

LLM calls are expensive. By running GLiNER + spaCy first and fetching graph context, Claude's input is pre-structured — shorter prompts, more accurate outputs, lower cost per chunk.

### Deduplication
- Exact name match → always merge.
- Embedding cosine similarity above threshold → merge candidate sent to LLM for confirmation.
- `merge_with_id` from LLM extraction → merge directly.
- Merge confidence threshold is configurable.

### Graph Schema (Neo4j)
```cypher
// Chunk nodes — stored with their embedding vector
(:Chunk {id, text, source_id, page, position, embedding[]})

// Entity nodes — also embedded for dedup
(:Entity {id, name, type, description, source_ids[], embedding[]})

// Structural edges
(:Entity)-[:RELATION {type, weight, confidence, chunk_id}]->(:Entity)

// Provenance edges — chunk to every entity it produced
(:Chunk)-[:MENTIONS {confidence}]->(:Entity)
(:Chunk)-[:FROM_SOURCE]->(:Source)

// Source metadata
(:Source {id, name, connector_type, ingested_at, raw_path})

// Vector indexes (Neo4j 5 native)
// CREATE VECTOR INDEX chunk_embeddings FOR (c:Chunk) ON (c.embedding)
//   OPTIONS {indexConfig: {`vector.dimensions`: 768, `vector.similarity_function`: 'cosine'}}
// CREATE VECTOR INDEX entity_embeddings FOR (e:Entity) ON (e.embedding)
//   OPTIONS {indexConfig: {`vector.dimensions`: 768, `vector.similarity_function`: 'cosine'}}
```

---

## Chatbot — Vector-Graph RAG Query Layer

Retrieval runs two paths in parallel, then merges them before calling Claude.

### Path A — Vector Search (semantic similarity)
1. Embed the user's question with the same `sentence-transformers` model used at ingest time.
2. Query the `chunk_embeddings` vector index in Neo4j for the top-K most similar chunks.
3. Return the raw chunk texts and their scores.

```cypher
CALL db.index.vector.queryNodes('chunk_embeddings', $k, $query_embedding)
YIELD node AS chunk, score
RETURN chunk.text, chunk.source_id, score
```

### Path B — Graph Traversal (structural context)
1. From the question, extract named entities (GLiNER on the query, fast).
2. Look up those entities in Neo4j by name (exact + fuzzy).
3. Follow `MENTIONS` edges inward: find chunks that produced these entities.
4. Traverse `RELATION` edges N hops outward from the entities: build a subgraph of connected nodes.

```cypher
// anchor on entities found in the question
MATCH (e:Entity) WHERE e.name IN $question_entities
// get the chunks that mentioned them
OPTIONAL MATCH (c:Chunk)-[:MENTIONS]->(e)
// traverse relations N hops
OPTIONAL MATCH path = (e)-[:RELATION*1..2]-(neighbor:Entity)
RETURN e, collect(DISTINCT c) as chunks, collect(DISTINCT neighbor) as neighbors
```

### Merge & Generate
- Deduplicate chunks across both paths (a chunk may appear in both).
- Rank by: vector score + graph centrality (entities with more connections rank higher).
- Serialize: top-K chunk texts + subgraph triples as context.
- Feed to Claude with the original question → streamed answer with source citations.

### Why both paths?
Vector search finds semantically similar text but has no notion of connections — it may miss a critical fact that's two hops away from the query topic. Graph traversal follows explicit relationships but only from named anchors — it misses context that uses different phrasing. Together they cover both.

| | Vector path | Graph path |
|---|---|---|
| Entry point | Semantic similarity | Named entity lookup |
| Strength | Finds rephrased / paraphrased content | Follows explicit relationships |
| Weakness | No structural awareness | Anchored to exact entities mentioned |

---

## Project Structure

```
knowledge-graph-lattice/
├── PLAN.md
├── docker-compose.yml
├── .env.example
│
├── backend/
│   ├── main.py                  # FastAPI entrypoint
│   ├── config.py
│   ├── models/
│   │   ├── document.py          # Pydantic models: Document, Chunk, Entity, Triple
│   │   └── graph.py
│   ├── connectors/
│   │   ├── base.py              # Abstract Connector class
│   │   ├── filesystem.py
│   │   ├── web.py
│   │   ├── database.py
│   │   └── api.py
│   ├── ingestion/
│   │   ├── pipeline.py          # Orchestrates connector → chunker → embedder → extractor → store
│   │   ├── chunker.py
│   │   └── embedder.py          # sentence-transformers wrapper; embeds chunks + entities
│   ├── extraction/
│   │   ├── ml_extractor.py      # Stage 1: GLiNER NER + spaCy dependency parse
│   │   ├── graph_context.py     # Pre-extraction Neo4j query (labels, rel types, fuzzy matches)
│   │   ├── llm_extractor.py     # Stage 2: Claude extraction with graph context
│   │   └── dedup.py             # Embedding-based merge candidates
│   ├── graph/
│   │   ├── base.py              # GraphDBPlugin abstract interface
│   │   ├── falkordb.py          # FalkorDB plugin (default)
│   │   ├── neo4j.py             # Neo4j plugin (future)
│   │   ├── memgraph.py          # Memgraph plugin (future)
│   │   ├── kuzu.py              # Kuzu plugin (future)
│   │   └── factory.py           # Reads GRAPH_DB_PLUGIN env var, returns the right plugin
│   ├── chat/
│   │   ├── vector_retriever.py  # Path A: vector search on chunk embeddings
│   │   ├── graph_retriever.py   # Path B: entity lookup + N-hop traversal
│   │   ├── merger.py            # Merge + rank results from both paths
│   │   └── chatbot.py           # Claude-powered Q&A with merged context
│   └── api/
│       ├── ingest.py            # POST /ingest endpoints
│       ├── graph.py             # GET /graph endpoints
│       └── chat.py              # POST /chat endpoint
│
└── frontend/
    ├── app/
    │   ├── page.tsx             # Home / chat
    │   ├── graph/page.tsx       # Graph visualization
    │   └── sources/page.tsx     # Manage data sources
    ├── components/
    │   ├── ChatInterface.tsx
    │   ├── GraphViewer.tsx
    │   └── SourceManager.tsx
    └── lib/
        └── api.ts
```

---

## Build Phases

### Phase 1 — Core Pipeline (start here)
- [ ] `Document`, `Chunk`, `Triple`, `ExtractionContext` data models
- [ ] File system connector (PDF + plain text first)
- [ ] Text chunking (fixed-size with overlap)
- [ ] Chunk embedder (`sentence-transformers`, runs parallel to ML extraction)
- [ ] Neo4j vector index creation on startup (`chunk_embeddings`, `entity_embeddings`)
- [ ] Stage 1: GLiNER + spaCy ML extractor
- [ ] Graph context fetch (Cypher queries for labels, rel types, fuzzy entity matches)
- [ ] Stage 2: Claude LLM extractor (receives chunk + ML output + graph context)
- [ ] `GraphDBPlugin` abstract interface (`base.py`)
- [ ] `factory.py` (reads `GRAPH_DB_PLUGIN` env var, instantiates the right plugin)
- [ ] FalkorDB plugin: write Chunk nodes with embeddings, Entity nodes, RELATION + MENTIONS edges, schema tracking in Redis hash
- [ ] Basic FastAPI: `POST /ingest/file`, `GET /graph/nodes`, `GET /graph/edges`
- [ ] Docker Compose with FalkorDB

### Phase 2 — More Connectors
- [ ] CSV / Excel connector (structured → triples via LLM column understanding)
- [ ] Web/URL connector (crawl + extract)
- [ ] JSON / XML connector
- [ ] Database connector (SQLAlchemy introspect + query)

### Phase 3 — Chatbot
- [ ] Path A: vector retriever (embed query → `db.index.vector.queryNodes` on chunk embeddings)
- [ ] Path B: graph retriever (GLiNER on query → entity lookup → N-hop traversal)
- [ ] Merger: deduplicate + rank chunks from both paths
- [ ] Claude chatbot endpoint with streamed responses
- [ ] Source citations in answers (chunk.source_id → original document + page)

### Phase 4 — Frontend
- [ ] Next.js app scaffold
- [ ] Chat UI (streaming)
- [ ] Graph visualization (interactive, click to explore)
- [ ] Source manager (upload files, add URLs, configure DB connections)

### Phase 5 — Polish
- [ ] Entity deduplication with embeddings
- [ ] Graph diff / incremental updates (re-ingest without full rebuild)
- [ ] Confidence scoring on extracted triples
- [ ] Export graph (JSON-LD, RDF/Turtle)

---

## Open Questions / Decisions to Make

1. **Chunk size** — how large should chunks be for extraction? Larger = more context but more hallucination risk. Start at ~1000 tokens with 200 overlap.
2. **GLiNER label seeding** — on first ingest (empty graph) GLiNER needs initial label hints. Use a generic seed list: `["Person", "Organization", "Location", "Product", "Event", "Concept", "Date", "Technology"]`. After first ingest, derive labels from `db.labels()`.
3. **Graph context fetch size** — how many existing entities to return as fuzzy candidates? Too many bloats the Claude prompt. Cap at 20 candidates, ranked by name similarity.
4. **Entity dedup threshold** — cosine similarity cutoff for merging entities. Tunable, start at 0.92.
5. **Graph granularity** — how fine-grained should relations be? LLM decides but prompt engineering matters.
6. **Multi-hop limit** — how many hops to traverse during retrieval? Start at 2, make configurable.
7. **Neo4j vs alternatives** — Neo4j Community is free but single-node. Could use Memgraph (open source, fast) or FalkorDB. Stick with Neo4j for now due to ecosystem.
8. **Frontend first or API first?** — API first. Build a working pipeline before any UI.

---

## Non-Goals (for now)

- Real-time streaming ingestion
- Multi-user auth / tenancy
- Graph versioning / time-travel
- On-premise LLM (Ollama etc.) — Claude only for now
- Production deployment / Kubernetes
