"""
backend.workflow
----------------
High-level orchestration layer — wires all extraction stages together.

Modules
-------
ingest.py   — end-to-end ingest pipeline (normalise → embed → extract → write)
"""

from .ingest import IngestPipeline, IngestSummary, ChunkStats

__all__ = [
    "IngestPipeline",
    "IngestSummary",
    "ChunkStats",
]
