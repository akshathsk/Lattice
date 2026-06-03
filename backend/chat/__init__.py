"""
backend.chat
------------
RAG query layer — retrieves context from the knowledge graph and answers
natural-language questions via GPT-4o.

Modules
-------
retriever.py  — two-path retrieval (vector chunks + entity-anchored graph traversal)
chatbot.py    — GPT-4o over retrieved context, streamed
"""

from .retriever import Retriever, RetrievalResult, RankedChunk
from .chatbot   import Chatbot

__all__ = [
    "Retriever",
    "RetrievalResult",
    "RankedChunk",
    "Chatbot",
]
