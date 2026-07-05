"""
File normaliser — reads uploaded documents and produces NormalisedChunks.

Supported formats
-----------------
.txt  .md          Plain text, read as-is.
.pdf               Extracted via pypdf (page-by-page).
.docx              Extracted via python-docx (paragraph-by-paragraph).
.csv               Each row serialised as "col: val, col: val …".
.json              Objects / arrays flattened to key-value text lines.
"""

from __future__ import annotations

import csv
import json
import logging
from pathlib import Path
from typing import Any

from .base    import BaseNormaliser
from .chunker import chunk_record
from .models  import NormalisedChunk

logger = logging.getLogger(__name__)


class FileNormaliser(BaseNormaliser):
    SOURCE = "file"

    def __init__(self, file_paths: list[str]) -> None:
        self._paths = [Path(p) for p in file_paths]

    def health_check(self) -> bool:
        return all(p.exists() for p in self._paths)

    def normalise(self, *, query=None, tables=None, collections=None) -> list[NormalisedChunk]:
        chunks: list[NormalisedChunk] = []
        for path in self._paths:
            try:
                chunks.extend(self._process(path))
            except Exception as e:
                logger.warning("Failed to process %s: %s", path.name, e)
        return chunks

    # ── per-format extraction ─────────────────────────────────────────────────

    def _process(self, path: Path) -> list[NormalisedChunk]:
        suffix = path.suffix.lower()
        if suffix in (".txt", ".md"):
            text = path.read_text(errors="replace")
            return self._to_chunks(text, path)
        if suffix == ".pdf":
            return self._process_pdf(path)
        if suffix == ".docx":
            return self._process_docx(path)
        if suffix == ".csv":
            return self._process_csv(path)
        if suffix == ".json":
            return self._process_json(path)
        # fallback: try reading as text
        text = path.read_text(errors="replace")
        return self._to_chunks(text, path)

    def _process_pdf(self, path: Path) -> list[NormalisedChunk]:
        from pypdf import PdfReader
        reader = PdfReader(str(path))
        pages: list[str] = []
        for page in reader.pages:
            t = page.extract_text() or ""
            if t.strip():
                pages.append(t)
        text = "\n\n".join(pages)
        return self._to_chunks(text, path)

    def _process_docx(self, path: Path) -> list[NormalisedChunk]:
        import docx
        doc = docx.Document(str(path))
        text = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
        return self._to_chunks(text, path)

    def _process_csv(self, path: Path) -> list[NormalisedChunk]:
        import pandas as pd
        df = pd.read_csv(str(path))
        lines = []
        for _, row in df.iterrows():
            parts = [f"{col}: {val}" for col, val in row.items() if str(val) not in ("nan", "")]
            if parts:
                lines.append(", ".join(parts))
        text = "\n".join(lines)
        return self._to_chunks(text, path)

    def _process_json(self, path: Path) -> list[NormalisedChunk]:
        data = json.loads(path.read_text())
        text = _json_to_text(data)
        return self._to_chunks(text, path)

    # ── shared chunker ────────────────────────────────────────────────────────

    def _to_chunks(self, text: str, path: Path) -> list[NormalisedChunk]:
        if not text.strip():
            return []
        indexed = chunk_record(text, record_id=path.name, collection=path.name)
        return [
            NormalisedChunk(
                source      = self.SOURCE,
                database    = "upload",
                collection  = path.name,
                record_id   = path.name,
                chunk_index = idx,
                text        = chunk,
                metadata    = {"filename": path.name, "suffix": path.suffix},
            )
            for idx, chunk in indexed
        ]


# ── helpers ───────────────────────────────────────────────────────────────────

def _json_to_text(obj: Any, depth: int = 0) -> str:
    if isinstance(obj, dict):
        lines = []
        for k, v in obj.items():
            if isinstance(v, (dict, list)):
                lines.append(f"{k}:\n{_json_to_text(v, depth+1)}")
            else:
                lines.append(f"{k}: {v}")
        return "\n".join(lines)
    if isinstance(obj, list):
        return "\n".join(_json_to_text(item, depth) for item in obj if item is not None)
    return str(obj)
