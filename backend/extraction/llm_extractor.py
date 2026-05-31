"""
GPT-4o LLM extractor — final stage of the extraction pipeline.

What it does
------------
Receives:
  • The raw chunk text
  • spaCy results    (entity candidates + SVO relation hints)
  • GLiNER results   (domain-specific entity candidates)
  • Graph context    (existing schema, similar entities, neighbourhood edges)

Calls GPT-4o with structured output, returns:
  • list[Entity]   — ready to write to the graph via write_entities()
  • list[Relation] — ready to write to the graph via write_relations()

Merge logic
-----------
When graph_context surfaces an existing entity similar to a candidate,
the LLM can set ``merge_with_id`` on the extracted entity.  The extractor
then uses that ID directly — so FalkorDB's MERGE hits the existing node
instead of creating a duplicate.

Schema growth
-------------
GPT may introduce an entity type or relation type that isn't in the current
schema.  That's intentional — the graph plugin's write_entities() /
write_relations() automatically registers any new type into Redis,
so every subsequent chunk benefits from the discovery.

Usage
-----
    from extraction.llm_extractor import LLMExtractor

    extractor = LLMExtractor()
    entities, relations = extractor.extract(
        chunk_text    = chunk.text,
        spacy_result  = spacy_result,
        gliner_result = gliner_result,
        graph_context = graph_context,
    )
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel, Field

from graph.models import Entity, Relation

if True:  # TYPE_CHECKING guard — avoids circular imports at runtime
    from extraction.models import SpacyResult, GlinerResult
    from extraction.graph_context import GraphContext

# ── env ───────────────────────────────────────────────────────────────────────

_env_file = Path(__file__).parent.parent / ".env"
if _env_file.exists():
    load_dotenv(_env_file)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL   = os.getenv("OPENAI_MODEL", "gpt-4o")

logger = logging.getLogger(__name__)

# ── structured output schema (what GPT must return) ───────────────────────────

class _LLMEntity(BaseModel):
    """One entity extracted by GPT.

    Note: no default values — OpenAI strict structured outputs require
    every field to be listed in the JSON schema's ``required`` array.
    Optional fields use ``X | None`` (nullable) with no Python default.
    """
    text:          str
    type:          str
    merge_with_id: str | None  # null = new entity; string = merge with existing ID


class _LLMRelation(BaseModel):
    """One directed relationship extracted by GPT."""
    source: str  # entity text — must appear in entities list
    target: str  # entity text — must appear in entities list
    type:   str  # SCREAMING_SNAKE_CASE, e.g. PARTY_TO


class _LLMOutput(BaseModel):
    """Full structured output from GPT."""
    entities:  list[_LLMEntity]
    relations: list[_LLMRelation]


# ── system prompt ─────────────────────────────────────────────────────────────

_SYSTEM = """\
You are a knowledge-graph extraction engine. Your job is to extract entities \
and relationships from a text chunk and return them as structured JSON.

## Rules

### Entities
1. Extract every meaningful named entity — people, organisations, contracts, \
regulations, clauses, obligations, locations, dates, products, technologies, etc.
2. Use a type from `existing_entity_types` when it fits. Only introduce a new \
type if none of the existing ones are appropriate.
3. If `similar_existing_entities` contains a close match for an entity you find, \
set `merge_with_id` to that entity's `existing_id`. This prevents duplicates.
4. Ignore structural metadata in the text (e.g. lines like \
"[Table: contracts | ID: 3]" or "[Collection: emails | ID: abc]").
5. Normalise surface forms: strip trailing punctuation, expand obvious \
abbreviations only when the full form appears nearby.

### Relations
1. Extract directed relationships between entities you have listed.
2. Use a type from `existing_relation_types` when it fits.
3. New relation types must be SCREAMING_SNAKE_CASE.
4. Prefer specific types (PARTY_TO, GOVERNS, OBLIGATES, REFERENCES) over \
generic ones (RELATED_TO).

### Quality
- Be comprehensive — the ML hints are a starting point, not a complete list.
- Do not hallucinate entities or relationships that are not in the text.
- Each entity in a relation must appear in the entities list.
"""


# ── extractor ─────────────────────────────────────────────────────────────────

class LLMExtractor:
    """
    GPT-4o extraction stage.

    Parameters
    ----------
    model   : OpenAI model name (default from OPENAI_MODEL env var → gpt-4o).
    api_key : OpenAI API key   (default from OPENAI_API_KEY env var).
    """

    def __init__(
        self,
        model:   str = OPENAI_MODEL,
        api_key: str = OPENAI_API_KEY,
    ) -> None:
        self._model  = model
        self._client = OpenAI(api_key=api_key)

    # ── public ────────────────────────────────────────────────────────────────

    def extract(
        self,
        chunk_text:    str,
        spacy_result:  "SpacyResult",
        gliner_result: "GlinerResult",
        graph_context: "GraphContext",
    ) -> tuple[list[Entity], list[Relation]]:
        """
        Run GPT-4o on one chunk and return graph-ready objects.

        Parameters
        ----------
        chunk_text    : Raw text of the NormalisedChunk.
        spacy_result  : Output from SpacyExtractor.extract().
        gliner_result : Output from GlinerExtractor.extract().
        graph_context : Output from GraphContextFetcher.fetch().

        Returns
        -------
        (entities, relations) — ready to pass to graph.write_entities()
        and graph.write_relations().
        """
        messages = self._build_messages(
            chunk_text, spacy_result, gliner_result, graph_context
        )

        logger.debug("LLM: calling %s …", self._model)
        completion = self._client.beta.chat.completions.parse(
            model           = self._model,
            messages        = messages,
            response_format = _LLMOutput,
        )

        llm_output = completion.choices[0].message.parsed
        logger.debug(
            "LLM: %d entities, %d relations | %d tokens",
            len(llm_output.entities),
            len(llm_output.relations),
            completion.usage.total_tokens,
        )

        entities, relations = self._to_graph_objects(llm_output)
        return entities, relations

    # ── message construction ──────────────────────────────────────────────────

    def _build_messages(
        self,
        chunk_text:    str,
        spacy_result:  "SpacyResult",
        gliner_result: "GlinerResult",
        graph_context: "GraphContext",
    ) -> list[dict[str, str]]:
        """Build the messages list sent to GPT."""

        user_content = _USER_TEMPLATE.format(
            graph_context = json.dumps(graph_context.to_prompt_dict(), indent=2),
            ml_hints      = json.dumps(_build_ml_hints(spacy_result, gliner_result), indent=2),
            chunk_text    = chunk_text.strip(),
        )

        return [
            {"role": "system", "content": _SYSTEM},
            {"role": "user",   "content": user_content},
        ]

    # ── output conversion ─────────────────────────────────────────────────────

    def _to_graph_objects(
        self,
        output: _LLMOutput,
    ) -> tuple[list[Entity], list[Relation]]:
        """
        Convert GPT's structured output to graph.Entity / graph.Relation objects.

        Merge logic
        -----------
        If ``merge_with_id`` is set, we use that ID directly so FalkorDB's
        MERGE statement hits the existing node and updates it in-place.
        Otherwise we generate a new stable ID from type + name.
        """
        entities:   list[Entity]  = []
        # text → entity.id map for wiring up relations
        name_to_id: dict[str, str] = {}

        for e in output.entities:
            text = e.text.strip()
            if not text:
                continue

            if e.merge_with_id:
                # Reuse existing node ID — MERGE will update, not insert
                entity = Entity(
                    id   = e.merge_with_id,
                    name = text,
                    type = e.type,
                )
            else:
                entity = Entity.make(
                    name  = text,
                    type_ = e.type,
                )

            entities.append(entity)
            name_to_id[text] = entity.id
            # Also register under the original surface form in case it differs
            name_to_id[e.text] = entity.id

        relations: list[Relation] = []
        for r in output.relations:
            src_id = name_to_id.get(r.source.strip())
            dst_id = name_to_id.get(r.target.strip())
            if not src_id or not dst_id:
                logger.debug(
                    "LLM: dropping relation %r -[%s]-> %r (entity not found)",
                    r.source, r.type, r.target,
                )
                continue
            relations.append(
                Relation(
                    source_id = src_id,
                    target_id = dst_id,
                    type      = r.type,
                )
            )

        return entities, relations


# ── helpers ───────────────────────────────────────────────────────────────────

_USER_TEMPLATE = """\
## Graph context
{graph_context}

## ML extraction hints (spaCy + GLiNER)
{ml_hints}

## Text chunk
{chunk_text}
"""


def _build_ml_hints(
    spacy_result:  "SpacyResult",
    gliner_result: "GlinerResult",
) -> dict[str, Any]:
    """Merge spaCy + GLiNER hints into one compact dict for the prompt."""
    spacy_dict  = spacy_result.to_prompt_dict()
    gliner_dict = gliner_result.to_prompt_dict()

    # Deduplicate entities across both sources by text
    seen:       set[str]        = set()
    all_entities: list[dict]    = []

    for ent in spacy_dict.get("entities", []):
        if ent["text"] not in seen:
            seen.add(ent["text"])
            all_entities.append({**ent, "source": "spacy"})

    for ent in gliner_dict.get("entities", []):
        if ent["text"] not in seen:
            seen.add(ent["text"])
            all_entities.append({**ent, "source": "gliner"})

    return {
        "entities":  all_entities,
        "relations": spacy_dict.get("relations", []),   # only spaCy does SVO
        "gliner_skipped": gliner_dict.get("skipped", False),
    }
