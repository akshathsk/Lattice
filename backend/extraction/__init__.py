"""
backend.extraction
------------------
Extraction pipeline — takes NormalisedChunk objects and populates the graph.

Stages (built incrementally):
  1. embedder.py       — sentence-transformers → 768-dim vectors  ✓
  2. ml_extractor.py   — GLiNER + spaCy → entities + relations    (next)
  3. graph_context.py  — query FalkorDB for existing schema        (next)
  4. llm_extractor.py  — Claude → refined structured output        (next)
"""

from .embedder import embed_chunks, embed_text, embed_texts, MODEL_NAME, EMBEDDING_DIM

__all__ = [
    "embed_chunks",
    "embed_text",
    "embed_texts",
    "MODEL_NAME",
    "EMBEDDING_DIM",
]
