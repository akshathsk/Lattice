"""
Text chunker — splits long strings into overlapping, word-boundary-aligned
windows suitable for embedding models (typically 256–512 tokens).

Design decisions
----------------
* Word-boundary splits  : never cuts mid-word; searches backward from the
                          target end position for the last whitespace.
* Sentence-boundary bias: before the word-boundary search, tries to split at
                          the last sentence terminator (. ! ?) within the
                          window — produces more semantically complete chunks.
* Overlap               : the tail of each chunk is prepended to the next so
                          that entities straddling a boundary are captured in
                          full by at least one chunk.
* Pure text / no deps   : no external tokeniser required; character counts are
                          used as a proxy for token counts (1 token ≈ 4 chars
                          for English prose, so the default 2 048-char window
                          ≈ 512 tokens).
"""

from __future__ import annotations

import re

# Sentence terminators we'll try to split on.
_SENTENCE_END = re.compile(r"[.!?]\s+")

# Default values (tunable via env or caller kwargs).
DEFAULT_CHUNK_SIZE = 2_048   # characters  (≈ 512 tokens)
DEFAULT_OVERLAP    = 256     # characters  (≈ 64 tokens)


def chunk_text(
    text:    str,
    size:    int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_OVERLAP,
) -> list[str]:
    """
    Split *text* into overlapping chunks of at most *size* characters.

    Parameters
    ----------
    text    : Input string (any length).
    size    : Maximum characters per chunk.
    overlap : Characters from the end of the previous chunk prepended to the
              next chunk (keeps context across boundaries).

    Returns
    -------
    List of non-empty strings.  A text shorter than *size* is returned as-is
    inside a single-element list.
    """
    text = text.strip()
    if not text:
        return []
    if len(text) <= size:
        return [text]

    chunks: list[str] = []
    start = 0

    while start < len(text):
        end = min(start + size, len(text))

        if end < len(text):
            # 1. Try sentence boundary inside the window.
            window = text[start:end]
            last_sentence = None
            for m in _SENTENCE_END.finditer(window):
                last_sentence = m
            if last_sentence and last_sentence.end() > overlap:
                end = start + last_sentence.end()
            else:
                # 2. Fall back to word boundary.
                word_boundary = text.rfind(" ", start, end)
                if word_boundary > start:
                    end = word_boundary

        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)

        # Advance, pulling back by `overlap` to create the sliding window.
        if end >= len(text):
            break
        start = max(start + 1, end - overlap)

    return chunks


def chunk_record(
    text:       str,
    record_id:  str,
    collection: str,
    *,
    size:       int = DEFAULT_CHUNK_SIZE,
    overlap:    int = DEFAULT_OVERLAP,
) -> list[tuple[int, str]]:
    """
    Convenience wrapper: returns ``[(chunk_index, chunk_text), …]``.
    Always yields at least one entry even for empty strings (empty text
    produces a single empty chunk so callers don't silently lose records).
    """
    parts = chunk_text(text, size=size, overlap=overlap)
    if not parts:
        parts = [""]
    return list(enumerate(parts))
