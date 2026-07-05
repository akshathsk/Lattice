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

from .base          import BaseNormaliser
from .chunker       import chunk_text, chunk_record, DEFAULT_CHUNK_SIZE, DEFAULT_OVERLAP
from .models        import NormalisedChunk
from .postgres      import PostgresNormaliser
from .mongo         import MongoNormaliser
from .file          import FileNormaliser
from .mysql         import MySQLNormaliser
from .elasticsearch import ElasticsearchNormaliser
from .rest_api      import RestApiNormaliser
from .s3            import S3Normaliser

__all__ = [
    "BaseNormaliser",
    "NormalisedChunk",
    "PostgresNormaliser",
    "MongoNormaliser",
    "FileNormaliser",
    "MySQLNormaliser",
    "ElasticsearchNormaliser",
    "RestApiNormaliser",
    "S3Normaliser",
    "get_normaliser",
    "chunk_text",
    "chunk_record",
    "DEFAULT_CHUNK_SIZE",
    "DEFAULT_OVERLAP",
]


def get_normaliser(source: str, **kwargs) -> BaseNormaliser:
    """
    Factory — return the right normaliser for *source*.

    source : ``"postgres"`` | ``"mongo"`` | ``"file"`` |
             ``"mysql"``   | ``"elasticsearch"`` |
             ``"rest"``    | ``"s3"``
    """
    registry: dict[str, type[BaseNormaliser]] = {
        "postgres":      PostgresNormaliser,
        "mongo":         MongoNormaliser,
        "file":          FileNormaliser,
        "mysql":         MySQLNormaliser,
        "elasticsearch": ElasticsearchNormaliser,
        "rest":          RestApiNormaliser,
        "s3":            S3Normaliser,
    }
    key = source.lower().strip()
    if key not in registry:
        raise ValueError(f"Unknown source {source!r}. Available: {sorted(registry)}")
    return registry[key](**kwargs)
