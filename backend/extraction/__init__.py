"""
backend.extraction
------------------
Extraction pipeline — takes NormalisedChunk objects and populates the graph.

Stages (built incrementally):
  1. embedder.py         — sentence-transformers → 768-dim vectors   ✓
  2. spacy_extractor.py  — NER + SVO dependency parse → hints        ✓
  3. gliner_extractor.py — zero-shot NER from live graph schema      ✓
  4. graph_context.py    — query FalkorDB for existing entities      ✓
  5. llm_extractor.py    — GPT-4o → refined structured output       (next)
"""

from .embedder          import embed_chunks, embed_text, embed_texts, MODEL_NAME, EMBEDDING_DIM
from .spacy_extractor   import SpacyExtractor
from .gliner_extractor  import GlinerExtractor
from .models            import (
    SpacyEntity, SpacyRelation, SpacyResult,
    GlinerEntity, GlinerResult,
)

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
    "GlinerExtractor",
    "GlinerEntity",
    "GlinerResult",
]
