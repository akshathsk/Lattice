# Lattice

An automated knowledge graph builder that ingests data from any source — structured or unstructured — extracts entities and relationships without a predefined schema using a hybrid ML + LLM pipeline, stores the result in a graph database, and exposes a chatbot interface to query it in natural language.

```
Data Sources (Postgres · MongoDB · …)
        │
        ▼
   Normalise                 chunk + convert to text  ✓
        │
        ▼
   Embed Chunks              768-dim vectors           ✓
        │
        ▼
   ML Extraction             spaCy NER + GLiNER        ✓
        │
        ▼
   Graph Context             KNN match existing nodes  ✓
        │
        ▼
   LLM Extraction            GPT-4o structured output  ✓
        │
        ▼
   FalkorDB                  entities + relations      ✓
        │
        ▼
   RAG Query Layer           vector + graph retrieval  ✗ pending
        │
        ▼
   Chatbot API               FastAPI + GPT-4o          ✗ pending
        │
        ▼
   Frontend                  Next.js chat + graph UI   ✗ pending
```

The graph schema emerges from the data — nothing is seeded at startup.
