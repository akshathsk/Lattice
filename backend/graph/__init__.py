"""
backend.graph
-------------
Graph database plugin layer.  The extraction pipeline and chatbot only ever
import from here — they never touch a specific backend directly.

Quick start
~~~~~~~~~~~
::

    from graph import get_graph_plugin

    g = get_graph_plugin("falkordb", host="localhost", port=6379)

    # write
    chunk_id = g.write_chunk(chunk, embedding)
    ids      = g.write_entities([entity1, entity2])
    g.write_relations([relation])
    g.write_mentions(chunk_id, ids)

    # read
    schema  = g.get_schema()
    similar = g.vector_search(query_embedding, k=5)
    matches = g.fuzzy_match_entities(entity_embedding, k=3)
    graph   = g.traverse(entity_id, hops=2)
"""

import os

from .base     import GraphDBPlugin
from .models   import Entity, Relation, ChunkResult, EntityResult, TraversalResult
from .falkordb import FalkorDBPlugin

__all__ = [
    "GraphDBPlugin",
    "Entity",
    "Relation",
    "ChunkResult",
    "EntityResult",
    "TraversalResult",
    "FalkorDBPlugin",
    "get_graph_plugin",
]

_REGISTRY: dict[str, type[GraphDBPlugin]] = {
    "falkordb": FalkorDBPlugin,
}


def get_graph_plugin(backend: str | None = None, **kwargs) -> GraphDBPlugin:
    """
    Factory — return the configured graph backend.

    *backend* defaults to the ``GRAPH_DB_PLUGIN`` environment variable
    (default: ``"falkordb"``).

    **kwargs are forwarded to the plugin's ``__init__``.
    """
    key = (backend or os.getenv("GRAPH_DB_PLUGIN", "falkordb")).lower().strip()
    if key not in _REGISTRY:
        raise ValueError(
            f"Unknown graph backend {key!r}. Available: {sorted(_REGISTRY)}"
        )
    return _REGISTRY[key](**kwargs)
