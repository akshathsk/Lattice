"""
Abstract base class for all source normalisers.

Every concrete normaliser (Postgres, Mongo, file …) must implement
``normalise()`` and return a flat list of ``NormalisedChunk`` objects.
The caller never needs to know which database is underneath.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from .models import NormalisedChunk


class BaseNormaliser(ABC):
    """
    Contract that every normaliser must satisfy.

    Parameters accepted by ``normalise()``
    ---------------------------------------
    query       : Source-specific query expression.
                  • SQL   → a raw SELECT string, e.g. ``"SELECT * FROM contracts WHERE status='active'"``
                  • Mongo → a filter dict, e.g.  ``{"related_party": "Acme Corp"}``
                  Ignored when *tables* / *collections* is also supplied;
                  a query always targets a single logical dataset.

    tables      : (SQL)   explicit list of table names to read.
    collections : (Mongo) explicit list of collection names to read.

    When neither *query* nor *tables*/*collections* is given the normaliser
    auto-discovers every table / collection in the connected database and
    reads all of them.
    """

    # Subclasses set this so log messages / chunk.source are consistent.
    SOURCE: str = "unknown"

    # ── public API ────────────────────────────────────────────────────────────

    @abstractmethod
    def normalise(
        self,
        *,
        query:       str | dict[str, Any] | None = None,
        tables:      list[str] | None            = None,
        collections: list[str] | None            = None,
    ) -> list[NormalisedChunk]:
        """
        Read data from the source and return normalised chunks.

        Implementations must be idempotent — calling ``normalise()`` twice
        must produce the same result (no side-effects on the source DB).
        """

    @abstractmethod
    def health_check(self) -> bool:
        """Return True if the underlying database is reachable."""

    # ── helpers shared by all subclasses ──────────────────────────────────────

    @staticmethod
    def _coerce_str(value: Any) -> str:
        """Safely convert any value to a clean string for text assembly."""
        if value is None:
            return ""
        if isinstance(value, (list, tuple)):
            return ", ".join(BaseNormaliser._coerce_str(v) for v in value)
        if isinstance(value, dict):
            return " ".join(
                f"{k}: {BaseNormaliser._coerce_str(v)}"
                for k, v in value.items()
                if v is not None
            )
        return str(value).strip()
