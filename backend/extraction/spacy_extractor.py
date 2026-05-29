"""
spaCy-based ML extractor.

What it does
------------
1. **NER** — detects named entities using spaCy's ``en_core_web_lg`` model
   and maps spaCy labels to the graph schema types (ORG → Organization, etc.).

2. **SVO relation extraction** — walks the dependency parse to find
   subject-verb-object triples where *both* ends are named entities.
   Handles:
     • Active voice  : nsubj → VERB → dobj / prep→pobj
     • Passive voice : nsubjpass + agent (by …)
     • Xcomp chains  : "agreed to pay" type constructs

The output (SpacyResult) is passed to the LLM extractor as structured hints
so GPT has a head-start on what entities and relations are present.

Model
-----
``en_core_web_lg`` — 587 MB, loaded once as a module singleton.
Pipes used: ner, parser (tok2vec + tagger are prerequisites).

Usage
-----
    from extraction.spacy_extractor import SpacyExtractor

    extractor = SpacyExtractor()
    result = extractor.extract(chunk.text)

    print(result.entities)    # list[SpacyEntity]
    print(result.relations)   # list[SpacyRelation]
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import spacy
from spacy.tokens import Doc, Span, Token

from .models import SpacyEntity, SpacyRelation, SpacyResult

if TYPE_CHECKING:
    from normalise.models import NormalisedChunk

logger = logging.getLogger(__name__)

# ── model singleton ───────────────────────────────────────────────────────────

MODEL_NAME = "en_core_web_lg"
_nlp: spacy.Language | None = None


def _get_nlp() -> spacy.Language:
    global _nlp
    if _nlp is None:
        logger.info("Loading spaCy model %s …", MODEL_NAME)
        _nlp = spacy.load(MODEL_NAME)
        logger.info("spaCy model loaded. Pipes: %s", _nlp.pipe_names)
    return _nlp


# ── label mapping ─────────────────────────────────────────────────────────────
# Maps spaCy NER labels → graph schema types (None = discard)

SPACY_TO_GRAPH: dict[str, str | None] = {
    "PERSON":     "Person",
    "ORG":        "Organization",
    "NORP":       "Organization",   # nationalities, political/religious groups
    "GPE":        "Location",       # geopolitical: countries, cities, states
    "LOC":        "Location",       # mountains, rivers, non-GPE locations
    "FAC":        "Location",       # buildings, airports, highways
    "PRODUCT":    "Product",
    "EVENT":      "Event",
    "WORK_OF_ART":"Concept",
    "LAW":        "Regulation",
    "DATE":       "Date",
    "TIME":       "Date",
    "LANGUAGE":   "Concept",
    "MONEY":      None,             # keep as metadata, not a graph entity
    "CARDINAL":   None,
    "ORDINAL":    None,
    "PERCENT":    None,
    "QUANTITY":   None,
}

# Dependency labels that indicate a subject role
_SUBJ_DEPS = {"nsubj", "nsubjpass", "csubj"}

# Dependency labels that indicate an object role
_OBJ_DEPS  = {"dobj", "attr", "oprd"}

# Preposition dependency label (leads to pobj)
_PREP_DEP  = "prep"
_POBJ_DEP  = "pobj"

# Passive agent ("governed by California")
_AGENT_DEP = "agent"


# ── extractor ─────────────────────────────────────────────────────────────────

class SpacyExtractor:
    """
    Stateless wrapper around spaCy's NER + dependency parser.

    The underlying nlp model is loaded once (module singleton) and reused.
    """

    def __init__(self, model_name: str = MODEL_NAME) -> None:
        self._model_name = model_name

    # ── public ────────────────────────────────────────────────────────────────

    def extract(self, text: str) -> SpacyResult:
        """
        Run NER + dependency parse on *text*, return a SpacyResult.

        Parameters
        ----------
        text : Raw text of one NormalisedChunk.

        Returns
        -------
        SpacyResult with deduplicated entities and SVO relations.
        """
        nlp = _get_nlp()
        doc = nlp(text)

        tok2ent    = self._build_tok2ent(doc)
        entities   = self._extract_entities(doc)
        relations  = self._extract_relations(doc, tok2ent)
        sentences  = [s.text.strip() for s in doc.sents]

        return SpacyResult(
            entities  = entities,
            relations = relations,
            sentences = sentences,
        )

    def extract_batch(self, texts: list[str]) -> list[SpacyResult]:
        """
        Batch extraction — more efficient than calling extract() in a loop.
        """
        nlp  = _get_nlp()
        docs = list(nlp.pipe(texts, batch_size=16))
        results = []
        for doc in docs:
            tok2ent   = self._build_tok2ent(doc)
            entities  = self._extract_entities(doc)
            relations = self._extract_relations(doc, tok2ent)
            sentences = [s.text.strip() for s in doc.sents]
            results.append(SpacyResult(entities=entities, relations=relations, sentences=sentences))
        return results

    # ── entity extraction ─────────────────────────────────────────────────────

    def _extract_entities(self, doc: Doc) -> list[SpacyEntity]:
        """
        Extract named entities from doc.ents, map labels, deduplicate by text.
        """
        seen:     set[str]          = set()
        entities: list[SpacyEntity] = []

        for ent in doc.ents:
            text = self._clean_span(ent)
            if not text or text in seen:
                continue
            seen.add(text)

            normalized = SPACY_TO_GRAPH.get(ent.label_)  # None = discard (but still record)
            sent_text  = ent.sent.text.strip()

            entities.append(
                SpacyEntity(
                    text            = text,
                    label           = ent.label_,
                    normalized_type = normalized,
                    start_char      = ent.start_char,
                    end_char        = ent.end_char,
                    sentence        = sent_text,
                )
            )

        return entities

    # ── relation extraction ───────────────────────────────────────────────────

    def _build_tok2ent(self, doc: Doc) -> dict[int, Span]:
        """Map every token index inside an entity span → that entity span."""
        tok2ent: dict[int, Span] = {}
        for ent in doc.ents:
            for token in ent:
                tok2ent[token.i] = ent
        return tok2ent

    def _extract_relations(
        self,
        doc:     Doc,
        tok2ent: dict[int, Span],
    ) -> list[SpacyRelation]:
        """
        Walk the dependency parse sentence by sentence.
        For each verb, collect entity subjects and entity objects,
        then emit (subject, verb_lemma, object) triples.
        """
        relations: list[SpacyRelation] = []
        seen_triples: set[tuple[str, str, str]] = set()

        for sent in doc.sents:
            sent_text = sent.text.strip()

            for token in sent:
                # Only examine main verbs (not auxiliaries)
                if token.pos_ not in ("VERB", "AUX") or token.dep_ == "aux":
                    continue

                subjects = self._collect_entities(token, _SUBJ_DEPS,  tok2ent)
                objects  = self._collect_entities(token, _OBJ_DEPS,   tok2ent)

                # Objects via prepositions:  VERB → prep → pobj
                for child in token.children:
                    if child.dep_ == _PREP_DEP:
                        for gc in child.children:
                            if gc.dep_ == _POBJ_DEP and gc.i in tok2ent:
                                objects.append(tok2ent[gc.i])

                # Passive agent:  "governed by California"
                for child in token.children:
                    if child.dep_ == _AGENT_DEP:
                        for gc in child.children:
                            if gc.i in tok2ent:
                                objects.append(tok2ent[gc.i])

                predicate = token.lemma_.lower()

                for subj_span in subjects:
                    for obj_span in objects:
                        subj_text = self._clean_span(subj_span)
                        obj_text  = self._clean_span(obj_span)

                        if not subj_text or not obj_text or subj_text == obj_text:
                            continue

                        subj_type = SPACY_TO_GRAPH.get(subj_span.label_)
                        obj_type  = SPACY_TO_GRAPH.get(obj_span.label_)

                        # Skip if either type is intentionally discarded
                        if subj_type is None or obj_type is None:
                            continue

                        triple = (subj_text, predicate, obj_text)
                        if triple in seen_triples:
                            continue
                        seen_triples.add(triple)

                        relations.append(
                            SpacyRelation(
                                subject       = subj_text,
                                subject_label = subj_type,
                                predicate     = predicate,
                                object        = obj_text,
                                object_label  = obj_type,
                                sentence      = sent_text,
                            )
                        )

        return relations

    def _collect_entities(
        self,
        token:    Token,
        dep_set:  set[str],
        tok2ent:  dict[int, Span],
    ) -> list[Span]:
        """Return entity spans that are direct children of *token* with a dep in *dep_set*."""
        spans: list[Span] = []
        for child in token.children:
            if child.dep_ in dep_set and child.i in tok2ent:
                spans.append(tok2ent[child.i])
        return spans

    # ── helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _clean_span(span: Span) -> str:
        """
        Strip leading determiners and trailing prepositions from a span.

        spaCy sometimes includes "the" or a trailing "with" inside an entity
        boundary (model imperfection).  Strip them here.
        """
        tokens = [t for t in span if t.pos_ not in ("DET",) and t.dep_ not in ("prep",)]
        return " ".join(t.text for t in tokens).strip()
