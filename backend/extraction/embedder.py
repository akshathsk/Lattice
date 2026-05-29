"""
Text embedder — converts NormalisedChunk text into 768-dim float vectors
using a locally-cached sentence-transformers model.

Model choice: ``all-mpnet-base-v2``
  • 768-dim output — matches the FalkorDB vector index created in startup.py
  • Strong semantic quality across domains (legal, technical, general)
  • ~420 MB download, cached after first run
  • CPU-friendly (no GPU required)

The model is loaded once as a module-level singleton and reused across calls.
Batching is used automatically — pass all chunks at once for best throughput.

Usage
-----
    from extraction.embedder import embed_chunks, embed_text

    # Embed a list of NormalisedChunk objects
    vectors = embed_chunks(chunks)          # list[list[float]], same order

    # Embed raw strings (for queries, entity names …)
    vec = embed_text("Acme Corp liability clause")   # list[float]
    vecs = embed_texts(["Acme Corp", "IBM"])          # list[list[float]]
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from sentence_transformers import SentenceTransformer

if TYPE_CHECKING:
    from normalise.models import NormalisedChunk

logger = logging.getLogger(__name__)

# ── model singleton ───────────────────────────────────────────────────────────

MODEL_NAME = "all-mpnet-base-v2"
EMBEDDING_DIM = 768

_model: SentenceTransformer | None = None


def _get_model() -> SentenceTransformer:
    """Load model on first call, reuse on subsequent calls."""
    global _model
    if _model is None:
        logger.info("Loading embedding model %s …", MODEL_NAME)
        _model = SentenceTransformer(MODEL_NAME)
        logger.info("Model loaded (dim=%d)", EMBEDDING_DIM)
    return _model


# ── public API ────────────────────────────────────────────────────────────────

def embed_chunks(chunks: list["NormalisedChunk"]) -> list[list[float]]:
    """
    Embed a list of NormalisedChunk objects.

    Returns a list of 768-dim float vectors in the same order as *chunks*.
    Pass all chunks at once — the model batches internally for efficiency.

    Parameters
    ----------
    chunks : List of NormalisedChunk objects (uses ``.text`` field).

    Returns
    -------
    List of embedding vectors, one per chunk.
    """
    if not chunks:
        return []
    texts = [c.text for c in chunks]
    return embed_texts(texts)


def embed_text(text: str) -> list[float]:
    """
    Embed a single string — for query embeddings, entity name lookups, etc.

    Returns a single 768-dim float vector.
    """
    return embed_texts([text])[0]


def embed_texts(texts: list[str]) -> list[list[float]]:
    """
    Embed a list of raw strings.

    Returns a list of 768-dim float vectors in the same order as *texts*.
    """
    if not texts:
        return []

    model = _get_model()
    logger.debug("Embedding %d text(s) …", len(texts))

    # encode() returns a numpy ndarray; convert to plain Python lists
    # so callers and FalkorDB never need numpy
    vectors = model.encode(
        texts,
        batch_size=32,
        show_progress_bar=False,
        normalize_embeddings=True,   # unit-length → cosine sim = dot product
        convert_to_numpy=True,
    )

    return [v.tolist() for v in vectors]
