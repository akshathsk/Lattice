"""
backend.extraction
------------------
Extraction pipeline — takes NormalisedChunk objects and populates the graph.

Stages (built incrementally):
  1. embedder.py        — sentence-transformers → 768-dim vectors   ✓
  2. spacy_extractor.py — NER + SVO dependency parse → hints        ✓
  3. graph_context.py   — query FalkorDB for existing schema        (next)
  4. llm_extractor.py   — GPT-4o → refined structured output       (next)
"""

from .embedder         import embed_chunks, embed_text, embed_texts, MODEL_NAME, EMBEDDING_DIM
from .spacy_extractor  import SpacyExtractor
from .models           import SpacyEntity, SpacyRelation, SpacyResult

__all__ = [
    "embed_chunks",
    "embed_text",
    "embed_texts",
    "MODEL_NAME",
    "EMBEDDING_DIM",
    "SpacyExtractor",
    "SpacyEntity",
    "SpacyRelation",
    "SpacyResult",
]
