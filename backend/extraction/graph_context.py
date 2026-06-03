"""
Graph context fetcher.

Queries FalkorDB *before* the LLM call to surface:
  1. The current schema  — what entity types and relation types already exist
  2. Similar entities    — existing graph nodes that might be the same as what
                           spaCy / GLiNER just found (deduplication signal)
  3. Local neighbourhood — edges already connecting those matched entities
                           (relation schema signal)

This context is injected into the GPT-4o prompt so the LLM:
  • Reuses existing entity types rather than inventing new ones
  • Merges near-duplicate entities instead of creating redundant nodes
  • Understands what relations already connect known entities
  • Adds genuinely new types only when nothing existing fits

Flow
----
    spacy_result  + gliner_result
          │
          ▼
    GraphContextFetcher.fetch()
      ├── get_schema()              → labels, rel_types
      ├── embed each candidate      → 768-dim vector per entity text
      ├── fuzzy_match_entities()    → similar existing entities (KNN)
      └── traverse() on each match → local neighbourhood edges
          │
          ▼
    GraphContext (structured dict for GPT prompt)

Usage
-----
    from extraction.graph_context import GraphContextFetcher
    from extraction.embedder import embed_text

    fetcher = GraphContextFetcher(graph)
    ctx     = fetcher.fetch(spacy_result, gliner_result)
    # ctx.to_prompt_dict() → injected into GPT system prompt
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

from extraction.embedder import embed_text

if TYPE_CHECKING:
    from graph.base import GraphDBPlugin
    from extraction.models import SpacyResult, GlinerResult

logger = logging.getLogger(__name__)


# ── output model ──────────────────────────────────────────────────────────────

class EntityMatch(BaseModel):
    """An existing graph entity that is similar to a candidate from ML extraction."""
    candidate:     str          # text from spaCy / GLiNER
    existing_id:   str          # graph node id
    existing_name: str          # canonical name in graph
    existing_type: str          # graph type label
    score:         float        # cosine distance (lower = more similar)


class GraphContext(BaseModel):
    """
    Full context snapshot passed to the LLM extractor.

    Fields
    ------
    schema_labels    : All entity type labels currently in the graph.
    schema_rel_types : All relationship type labels currently in the graph.
    entity_matches   : Existing entities similar to the ML candidates.
    neighbourhood    : Edges already connecting the matched entities.
    is_empty         : True when the graph has no entities yet (first run).
    """

    schema_labels:    list[str]          = Field(default_factory=list)
    schema_rel_types: list[str]          = Field(default_factory=list)
    entity_matches:   list[EntityMatch]  = Field(default_factory=list)
    neighbourhood:    list[dict[str, Any]] = Field(default_factory=list)
    is_empty:         bool               = False

    def to_prompt_dict(self) -> dict[str, Any]:
        """
        Compact representation injected into the GPT system prompt.

        Keeps only the information GPT needs:
          - existing schema     → use these types, don't invent new ones unless necessary
          - similar entities    → merge with these if the same real-world thing
          - existing relations  → context on how entities already connect
        """
        return {
            "graph_is_empty": self.is_empty,
            "existing_entity_types": self.schema_labels,
            "existing_relation_types": self.schema_rel_types,
            "similar_existing_entities": [
                {
                    "candidate":    m.candidate,
                    "existing_id":  m.existing_id,
                    "existing_name": m.existing_name,
                    "existing_type": m.existing_type,
                    "similarity":   round(1 - m.score, 3),  # convert distance → similarity
                }
                for m in self.entity_matches
            ],
            "existing_relations": [
                {
                    "src":  e.get("src_name", e.get("src")),
                    "rel":  e["type"],
                    "dst":  e.get("dst_name", e.get("dst")),
                }
                for e in self.neighbourhood
            ],
        }


# ── fetcher ───────────────────────────────────────────────────────────────────

class GraphContextFetcher:
    """
    Fetches graph context for a set of ML-extracted entity candidates.

    Parameters
    ----------
    graph          : Live GraphDBPlugin (FalkorDB).
    match_k        : Number of similar existing entities to retrieve per candidate.
    match_threshold: Cosine distance threshold — candidates above this are not
                     considered similar enough to be a match (0 = identical, 2 = opposite).
    max_hops       : Traversal depth when fetching neighbourhood edges.
    """

    def __init__(
        self,
        graph:           "GraphDBPlugin",
        match_k:         int   = 3,
        match_threshold: float = 0.25,
        max_hops:        int   = 1,
    ) -> None:
        self._graph           = graph
        self._match_k         = match_k
        self._match_threshold = match_threshold
        self._max_hops        = max_hops

    # ── public ────────────────────────────────────────────────────────────────

    def fetch(
        self,
        spacy_result:  "SpacyResult",
        gliner_result: "GlinerResult",
    ) -> GraphContext:
        """
        Build a GraphContext from the combined ML extraction output.

        Steps
        -----
        1. Pull schema from Redis.
        2. Collect unique entity candidate texts from spaCy + GLiNER.
        3. Embed each candidate and run KNN against existing Entity nodes.
        4. For each match found, run a 1-hop traversal to get nearby edges.
        5. Return a GraphContext ready for the LLM prompt.
        """
        schema = self._graph.get_schema()
        labels    = schema.get("labels", [])
        rel_types = schema.get("rel_types", [])

        # First ingestion: graph is completely empty
        if not labels:
            logger.debug("graph_context: graph is empty — returning empty context")
            return GraphContext(is_empty=True)

        # Collect unique candidate entity texts (spaCy + GLiNER combined)
        candidates = self._collect_candidates(spacy_result, gliner_result)
        logger.debug("graph_context: %d unique candidates to match", len(candidates))

        # Embed + match each candidate against existing entities
        matches: list[EntityMatch] = []
        matched_entity_ids: set[str] = set()

        for candidate_text in candidates:
            embedding = embed_text(candidate_text)
            similar   = self._graph.fuzzy_match_entities(
                embedding,
                k         = self._match_k,
                threshold = self._match_threshold,
            )
            for hit in similar:
                matches.append(EntityMatch(
                    candidate     = candidate_text,
                    existing_id   = hit.entity_id,
                    existing_name = hit.name,
                    existing_type = hit.type,
                    score         = hit.score,
                ))
                matched_entity_ids.add(hit.entity_id)

        # Fetch 1-hop neighbourhood for matched entities
        neighbourhood: list[dict[str, Any]] = []
        seen_edges: set[tuple[str, str, str]] = set()

        for entity_id in matched_entity_ids:
            try:
                traversal = self._graph.traverse(entity_id, hops=self._max_hops)
                for edge in traversal.edges:
                    key = (edge["src"], edge["type"], edge["dst"])
                    if key not in seen_edges:
                        seen_edges.add(key)
                        neighbourhood.append(edge)
            except Exception as e:
                logger.debug("graph_context: traversal failed for %s: %s", entity_id, e)

        logger.debug(
            "graph_context: %d matches, %d neighbourhood edges",
            len(matches), len(neighbourhood),
        )

        return GraphContext(
            schema_labels    = labels,
            schema_rel_types = rel_types,
            entity_matches   = matches,
            neighbourhood    = neighbourhood,
            is_empty         = False,
        )

    # ── helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _collect_candidates(
        spacy_result:  "SpacyResult",
        gliner_result: "GlinerResult",
    ) -> list[str]:
        """
        Return deduplicated entity candidate texts from both ML extractors.
        Discards spaCy entities with no normalized type (CARDINAL, MONEY …).
        """
        seen:  set[str]  = set()
        texts: list[str] = []

        for ent in spacy_result.entities:
            if ent.normalized_type and ent.text not in seen:
                seen.add(ent.text)
                texts.append(ent.text)

        for ent in gliner_result.entities:
            if ent.text not in seen:
                seen.add(ent.text)
                texts.append(ent.text)

        return texts
