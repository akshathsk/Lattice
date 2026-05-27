"""
backend.normalise
-----------------
Reads raw records from any data source and produces a flat list of
``NormalisedChunk`` objects ready for embedding and entity extraction.

Quick start
~~~~~~~~~~~
::

    from normalise import get_normaliser

    # PostgreSQL — read everything
    n = get_normaliser("postgres",
                       dbname="contracts", user="lattice", password="…")
    chunks = n.normalise()

    # PostgreSQL — specific tables
    chunks = n.normalise(tables=["contracts", "clauses"])

    # PostgreSQL — custom query
    chunks = n.normalise(query="SELECT * FROM contracts WHERE status='active'")

    # MongoDB — read everything
    n = get_normaliser("mongo", database="contracts_docs")
    chunks = n.normalise()

    # MongoDB — filter across selected collections
    chunks = n.normalise(
        collections=["emails", "memos"],
        query={"related_party": "Acme Corp"},
    )
"""

from .base     import BaseNormaliser
from .chunker  import chunk_text, chunk_record, DEFAULT_CHUNK_SIZE, DEFAULT_OVERLAP
from .models   import NormalisedChunk
from .postgres import PostgresNormaliser
from .mongo    import MongoNormaliser

__all__ = [
    "BaseNormaliser",
    "NormalisedChunk",
    "PostgresNormaliser",
    "MongoNormaliser",
    "get_normaliser",
    "chunk_text",
    "chunk_record",
    "DEFAULT_CHUNK_SIZE",
    "DEFAULT_OVERLAP",
]


def get_normaliser(source: str, **kwargs) -> BaseNormaliser:
    """
    Factory function — return the right normaliser for *source*.

    Parameters
    ----------
    source : ``"postgres"`` | ``"mongo"``
    **kwargs : Passed directly to the normaliser's ``__init__``.

    Raises
    ------
    ValueError if *source* is not recognised.
    """
    registry: dict[str, type[BaseNormaliser]] = {
        "postgres": PostgresNormaliser,
        "mongo":    MongoNormaliser,
    }
    key = source.lower().strip()
    if key not in registry:
        raise ValueError(
            f"Unknown source {source!r}. Available: {sorted(registry)}"
        )
    return registry[key](**kwargs)
