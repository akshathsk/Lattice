"""
Output models for the ML extraction stage.

These types flow from spaCy (and later GLiNER) into the LLM extractor,
which refines them into the final graph.Entity / graph.Relation objects.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class SpacyEntity(BaseModel):
    """
    A named entity detected by spaCy's NER pipeline.

    ``label``           : raw spaCy label (ORG, PERSON, GPE, LAW …)
    ``normalized_type`` : mapped graph label (Organization, Person, Location …)
                          None for labels we intentionally discard (CARDINAL etc.)
    ``sentence``        : the full sentence the entity appeared in — gives
                          the LLM surrounding context without passing the whole chunk.
    """

    text:             str
    label:            str        # raw spaCy label
    normalized_type:  str | None # mapped graph type; None = discard
    start_char:       int
    end_char:         int
    sentence:         str


class SpacyRelation(BaseModel):
    """
    A subject-verb-object triple extracted from the dependency parse.

    Both subject and object are named entities; predicate is the lemmatised
    verb connecting them.  The sentence is included for LLM context.
    """

    subject:       str
    subject_label: str   # normalized_type of the subject entity
    predicate:     str   # lemmatised verb, e.g. "sign", "govern", "obligate"
    object:        str
    object_label:  str   # normalized_type of the object entity
    sentence:      str


class SpacyResult(BaseModel):
    """
    Combined output of one spaCy extraction call on a single chunk.

    Passed directly to the LLM extractor as structured context.
    """

    entities:  list[SpacyEntity]  = Field(default_factory=list)
    relations: list[SpacyRelation] = Field(default_factory=list)
    sentences: list[str]           = Field(default_factory=list)

    def to_prompt_dict(self) -> dict:
        """
        Compact dict representation suitable for embedding in a GPT prompt.
        Drops discard-labelled entities and deduplicated surface forms.
        """
        seen: set[str] = set()
        ents = []
        for e in self.entities:
            if e.normalized_type and e.text not in seen:
                seen.add(e.text)
                ents.append({"text": e.text, "type": e.normalized_type})

        rels = [
            {
                "subject":   r.subject,
                "predicate": r.predicate,
                "object":    r.object,
            }
            for r in self.relations
        ]
        return {"entities": ents, "relations": rels}
