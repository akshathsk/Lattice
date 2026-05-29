"""
GLiNER-based zero-shot NER extractor.

What it does
------------
Uses GLiNER (Generalist Lightweight model for Named Entity Recognition) to
find entities in chunk text using the **live graph schema** as its label set.

Unlike spaCy (fixed labels baked into the model), GLiNER is told at runtime
what to look for — so it automatically searches for whatever entity types
have been discovered so far:

    First chunk   → schema empty → GLiNER skips → spaCy + GPT-4o alone
    Second chunk  → schema = {"Organization", "Contract", "Regulation", …}
                 → GLiNER actively hunts for those types
    N-th chunk    → schema has grown further → GLiNER finds more

Model
-----
``urchade/gliner_medium-v2.1`` (~300 MB, downloaded once, cached locally).
Loaded as a module singleton.

Label format
------------
The graph schema stores PascalCase labels ("Organization", "Contract").
GLiNER performs best with lowercase labels — they're downcased before the
call and mapped back to PascalCase in the output.

Usage
-----
    from graph import get_graph_plugin
    from extraction.gliner_extractor import GlinerExtractor

    graph     = get_graph_plugin("falkordb")
    extractor = GlinerExtractor()

    result = extractor.extract(chunk.text, graph)
    # result.skipped == True  when schema is empty (first run)
    # result.entities         list[GlinerEntity] with graph-schema labels
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from gliner import GLiNER

from .models import GlinerEntity, GlinerResult

if TYPE_CHECKING:
    from graph.base import GraphDBPlugin

logger = logging.getLogger(__name__)

# ── model singleton ───────────────────────────────────────────────────────────

MODEL_NAME = "urchade/gliner_medium-v2.1"
_model: GLiNER | None = None


def _get_model() -> GLiNER:
    global _model
    if _model is None:
        logger.info("Loading GLiNER model %s …", MODEL_NAME)
        _model = GLiNER.from_pretrained(MODEL_NAME)
        logger.info("GLiNER model loaded")
    return _model


# ── extractor ─────────────────────────────────────────────────────────────────

class GlinerExtractor:
    """
    Zero-shot NER extractor driven by the live graph schema.

    Parameters
    ----------
    threshold : GLiNER confidence threshold (0–1).
                Lower = more entities found but more noise.
                Higher = fewer entities but more precise.
                Default 0.5 is a good general starting point.
    """

    def __init__(self, threshold: float = 0.5) -> None:
        self.threshold = threshold

    # ── public ────────────────────────────────────────────────────────────────

    def extract(self, text: str, graph: "GraphDBPlugin") -> GlinerResult:
        """
        Run GLiNER on *text* using the current graph schema as labels.

        Parameters
        ----------
        text  : Raw text of one NormalisedChunk.
        graph : Live GraphDBPlugin — used to fetch the current schema.

        Returns
        -------
        GlinerResult.
          • ``skipped=True``  when schema has no labels yet (first run).
          • ``skipped=False`` with populated ``entities`` otherwise.
        """
        schema = graph.get_schema()
        labels = schema.get("labels", [])

        if not labels:
            logger.debug("GLiNER skipping — schema is empty (first ingestion run)")
            return GlinerResult(skipped=True)

        # GLiNER works best with lowercase labels
        lower_labels   = [l.lower() for l in labels]
        # Reverse map: lowercase → original PascalCase
        label_map      = {l.lower(): l for l in labels}

        logger.debug("GLiNER running with %d labels: %s", len(labels), labels)

        model    = _get_model()
        raw_ents = model.predict_entities(text, lower_labels, threshold=self.threshold)

        # Build sentence lookup for context (split on newlines + periods)
        sent_lookup = _sentence_lookup(text)

        entities: list[GlinerEntity] = []
        seen: set[str] = set()

        for ent in raw_ents:
            ent_text  = ent["text"].strip()
            ent_label = label_map.get(ent["label"], ent["label"])  # back to PascalCase
            ent_score = float(ent["score"])

            # Deduplicate same text+label within a chunk
            key = f"{ent_text}:{ent_label}"
            if key in seen:
                continue
            seen.add(key)

            sentence = _find_sentence(ent_text, sent_lookup)

            entities.append(
                GlinerEntity(
                    text     = ent_text,
                    label    = ent_label,
                    score    = ent_score,
                    sentence = sentence,
                )
            )

        logger.debug("GLiNER found %d entities", len(entities))

        return GlinerResult(
            entities    = entities,
            skipped     = False,
            labels_used = labels,
        )

    def extract_batch(
        self,
        texts: list[str],
        graph: "GraphDBPlugin",
    ) -> list[GlinerResult]:
        """
        Extract from multiple texts.

        Fetches the schema once, then loops over texts.
        More efficient than calling extract() per-text for the schema fetch.
        """
        schema = graph.get_schema()
        labels = schema.get("labels", [])

        if not labels:
            logger.debug("GLiNER skipping batch — schema is empty")
            return [GlinerResult(skipped=True) for _ in texts]

        lower_labels = [l.lower() for l in labels]
        label_map    = {l.lower(): l for l in labels}
        model        = _get_model()

        results: list[GlinerResult] = []

        for text in texts:
            raw_ents    = model.predict_entities(text, lower_labels, threshold=self.threshold)
            sent_lookup = _sentence_lookup(text)
            entities: list[GlinerEntity] = []
            seen: set[str] = set()

            for ent in raw_ents:
                ent_text  = ent["text"].strip()
                ent_label = label_map.get(ent["label"], ent["label"])
                key = f"{ent_text}:{ent_label}"
                if key in seen:
                    continue
                seen.add(key)
                entities.append(
                    GlinerEntity(
                        text     = ent_text,
                        label    = ent_label,
                        score    = float(ent["score"]),
                        sentence = _find_sentence(ent_text, sent_lookup),
                    )
                )

            results.append(GlinerResult(
                entities    = entities,
                skipped     = False,
                labels_used = labels,
            ))

        return results


# ── helpers ───────────────────────────────────────────────────────────────────

def _sentence_lookup(text: str) -> list[str]:
    """
    Split text into rough sentences for context lookup.
    Splits on newlines and sentence-ending punctuation.
    """
    import re
    parts = re.split(r"(?<=[.!?])\s+|\n", text)
    return [p.strip() for p in parts if p.strip()]


def _find_sentence(entity_text: str, sentences: list[str]) -> str:
    """Return the first sentence containing *entity_text*, or empty string."""
    for sent in sentences:
        if entity_text in sent:
            return sent
    return ""
