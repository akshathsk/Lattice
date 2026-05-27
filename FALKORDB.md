# FalkorDB — Architecture & Internals

> **Fork:** [github.com/akshathsk/FalkorDB-lattice](https://github.com/akshathsk/FalkorDB-lattice) (v4.18.8)
> **Upstream:** [github.com/FalkorDB/FalkorDB](https://github.com/FalkorDB/FalkorDB)

## What is FalkorDB?

FalkorDB is a **property graph database** that runs as a **Redis module**. It is not a standalone database — it loads into a Redis server process and extends Redis with graph capabilities. Redis itself becomes the host: it handles networking, persistence, replication, and memory management. FalkorDB adds the graph query engine on top.

It was originally created at Redis Ltd. as **RedisGraph**, then forked and relaunched as FalkorDB by former Redis engineers in 2023.

---

## The Underlying Database: Redis

FalkorDB is a Redis module (`RedisModule_OnLoad` in `src/module.c`). This means:

- Redis is the **actual database**. FalkorDB is a plugin loaded at startup via `loadmodule falkordb.so`.
- All data lives in Redis memory. Redis handles AOF/RDB persistence, replication, and clustering.
- The Redis allocator (`RedisModule_Alloc/Free`) is used for all memory — including GraphBLAS matrices and Rust heap allocations.
- The minimum supported Redis version is **8.0.0** (confirmed in `module.c`).
- FalkorDB registers two custom Redis data types: `GraphContextType` (the graph) and `GraphMetaType` (metadata).

The practical implication: you run FalkorDB by starting Redis with the module loaded, not by running a separate process. The default port is Redis's `6379`, plus an optional **Bolt protocol** port (Neo4j's wire protocol, `7687`) for compatibility with Neo4j drivers.

---

## Core Technology Stack

FalkorDB is built from five distinct subsystems:

### 1. Graph Traversal — GraphBLAS (SuiteSparse)

The adjacency structure of the graph is stored as **sparse matrices** using [SuiteSparse GraphBLAS](https://graphblas.org/). Each relationship type has its own matrix where `A[src_id, dest_id]` indicates an edge exists.

Graph traversal (e.g., multi-hop `MATCH` queries) is executed as **sparse matrix multiplication (SpGEMM)** — mathematically equivalent to BFS/DFS but parallelised via OpenMP and SIMD. This is why FalkorDB is significantly faster than pointer-chasing graph databases at traversal.

From `module.c`:
```c
// GraphBLAS is initialized via LAGraph, using Redis's allocator
LAGr_Init(GrB_NONBLOCKING, RedisModule_Alloc, ...)

// All matrices stored in CSR (Compressed Sparse Row) format
GrB_set(GrB_GLOBAL, GxB_BY_ROW, GxB_FORMAT)
```

Multi-edge scenarios (multiple edges between the same node pair) use a **Tensor** — a 3D matrix (`Delta_Matrix`) where each cell holds a `GrB_Vector` of edge IDs rather than a scalar.

The **Delta_Matrix** abstraction wraps GraphBLAS matrices with a pending-write buffer, allowing transactional batch commits.

### 2. Vector Search — RediSearch / VecSim (HNSW)

Vector indexing is handled by **RediSearch** (a FalkorDB fork, listed as a submodule). RediSearch uses the **VecSim** library internally, which implements **HNSW** (Hierarchical Navigable Small World) — the same algorithm used by Pinecone, Weaviate, and Qdrant.

Supported similarity functions: **Euclidean (L2)** and **Cosine**.

Configurable HNSW parameters (set at index creation time, not changeable after):

| Parameter | Default | Meaning |
|---|---|---|
| `dimension` | required | Embedding vector size — must match every stored vector |
| `M` | 16 | Max outgoing edges per HNSW graph node |
| `efConstruction` | 200 | Accuracy during index build (higher = slower build, better recall) |
| `efRuntime` | 10 | Accuracy during query (higher = slower query, better recall) |

**Important:** vector dimensions are fixed at index creation. Switching embedding models requires dropping and rebuilding the index.

### 3. Full-Text & Range Indexing — RediSearch

The same RediSearch dependency also powers full-text search (BM25 ranking, stemming, phonetic matching) and range/numeric indexing. Index field types from `index_field.h`:

```c
INDEX_FLD_FULLTEXT = 0x01  // full text (BM25)
INDEX_FLD_NUMERIC  = 0x02  // numeric range
INDEX_FLD_GEO      = 0x04  // geospatial
INDEX_FLD_STR      = 0x08  // string (exact match)
INDEX_FLD_VECTOR   = 0x10  // HNSW vector
```

Multiple types can be combined on a single field via bitwise OR.

### 4. Query Language — OpenCypher + libcypher-parser

Queries use **openCypher** (the ISO standard graph query language, also used by Neo4j, Memgraph, and Amazon Neptune). Parsing is handled by `libcypher-parser` (a submodule). The parsed AST goes through validation, planning, and execution phases in `src/ast/`, `src/execution_plan/`.

### 5. Rust Core — Memory & Undo Log

`deps/FalkorDB-core-rs` is a small Rust library that plugs into Redis's allocator via FFI:

```rust
// Rust's global allocator redirected to Redis's jemalloc-based allocator
// This ensures all Rust heap allocations are tracked by Redis memory accounting
unsafe impl GlobalAlloc for FalkorDBAlloc {
    unsafe fn alloc(&self, layout: Layout) -> *mut u8 {
        RedisModule_Alloc(size)
    }
}
```

It also implements the `undo_log` — the mechanism for rolling back failed write transactions. This is written in Rust for memory safety on the critical path of transaction management.

### 6. JavaScript UDFs — QuickJS

FalkorDB embeds **QuickJS** (a lightweight JS engine by Fabrice Bellard) for user-defined functions written in JavaScript. This lets you register custom Cypher functions without recompiling FalkorDB.

---

## Persistence & Serialization

FalkorDB uses Redis's persistence mechanisms (RDB snapshots and AOF logs). The graph is serialized using a custom binary format — currently **v19** (`src/serializers/decoders/current/v19/`). Decoders for older formats (v14–v18) are kept for backwards compatibility when loading older snapshots.

Graphs are saved as a registered Redis data type. On `SAVE`/`BGSAVE`, Redis calls FalkorDB's serializer to write the graph to the RDB file.

---

## Wire Protocol

FalkorDB supports two protocols:

1. **Redis protocol (RESP)** — the standard Redis wire protocol on port 6379. Queries sent as `GRAPH.QUERY <graph> <cypher>`.
2. **Bolt protocol** — Neo4j's binary wire protocol on a separate port (typically 7687). This allows Neo4j drivers (Python `neo4j`, JS `neo4j-driver`, etc.) to connect to FalkorDB without any code changes.

---

## Vector API (Cypher)

**Create a vector index:**
```cypher
CREATE VECTOR INDEX FOR (n:Chunk) ON (n.embedding) OPTIONS {
    dimension: 768,
    similarityFunction: 'cosine',
    M: 16,
    efConstruction: 200,
    efRuntime: 10
}
```

**Store a vector on a node:**
```cypher
CREATE (c:Chunk {text: $text, embedding: vecf32($float_array)})
```

**KNN search (returns nodes + distance score):**
```cypher
CALL db.idx.vector.queryNodes('Chunk', 'embedding', $k, vecf32($query))
YIELD node, score
```

**Chain vector search into graph traversal — one query, one round trip:**
```cypher
CALL db.idx.vector.queryNodes('Chunk', 'embedding', 10, vecf32($query))
YIELD node, score
MATCH (node)-[:MENTIONS]->(e:Entity)-[:RELATION*1..2]-(neighbor:Entity)
RETURN node.text, score, collect(neighbor.name)
```

**Inline distance functions:**
```cypher
RETURN vec.cosineDistance(n.embedding, vecf32($q))
RETURN vec.euclideanDistance(n.embedding, vecf32($q))
```

Note: `score` is **distance** (lower = more similar), not similarity.

---

## Dependency Map

```
FalkorDB
├── Redis                  ← host process, networking, persistence, memory
├── GraphBLAS (SuiteSparse) ← sparse matrix graph traversal + OpenMP parallelism
├── LAGraph                ← higher-level graph algorithms on top of GraphBLAS
├── RediSearch (FalkorDB fork) ← vector (HNSW/VecSim) + fulltext + range indexing
├── libcypher-parser       ← openCypher query parsing
├── QuickJS                ← JavaScript UDF engine
├── FalkorDB-core-rs (Rust) ← memory allocator bridge + undo log
├── rax                    ← radix tree (by antirez, Redis's author)
├── xxHash                 ← fast hashing
├── oniguruma              ← regex engine
├── libcsv                 ← CSV bulk import
└── libcurl                ← HTTP (used for remote data sources)
```

---

## Key Characteristics for This Project

| Property | Detail |
|---|---|
| **Language** | C (core) + Rust (memory/undo log) |
| **License** | SSPLv1 (same as MongoDB) — free to use, source-available, restrictions on offering as a managed service |
| **Persistence** | Redis RDB + AOF |
| **Clustering** | Via Redis Cluster |
| **Vector algo** | HNSW (same as Pinecone, Weaviate, Qdrant) |
| **Graph traversal** | GraphBLAS sparse matrix multiplication |
| **Query language** | openCypher (Neo4j compatible) |
| **Neo4j driver compat** | Yes — Bolt protocol support |
| **This version** | v4.18.8, serialization format v19 |
