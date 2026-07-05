"""Shared cleaning/chunking helpers used across all collection cleaners.

This module consolidates the four identical ``chunk_paragraphs``
implementations, the two copies of ``extract_topic_tags``, plus the
``split_book / split_chapter / extract_numeric / clean_text / safe_int``
helpers that appeared in both ``al_kafi_cleaner`` and
``nahjul_balaghah_cleaner``.
"""

from __future__ import annotations

import re

import pandas as pd

# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------
CHUNK_SIZE = 350
CHUNK_OVERLAP = 50


def chunk_paragraphs(
    text: str,
    *,
    chunk_size: int = CHUNK_SIZE,
    overlap: int = CHUNK_OVERLAP,
) -> list[str]:
    """Paragraph-aware chunking with word-level overlap.

    Splits on blank-line paragraph boundaries, then groups paragraphs into
    chunks that stay under *chunk_size* words while keeping *overlap* words
    between adjacent chunks for context continuity.
    """
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    for p in paragraphs:
        p_len = len(p.split())
        if current_len + p_len > chunk_size and current:
            chunks.append(" ".join(current))
            overlap_words = " ".join(" ".join(current).split()[-overlap:])
            current = [overlap_words, p]
            current_len = len(overlap_words.split()) + p_len
        else:
            current.append(p)
            current_len += p_len

    if current:
        chunks.append(" ".join(current))
    return chunks


# ---------------------------------------------------------------------------
# Topic extraction
# ---------------------------------------------------------------------------
_STOP_WORDS = frozenset({
    "the", "of", "and", "in", "on", "for", "to", "at", "by", "with",
    "from", "about", "between", "into", "through", "during", "before",
    "after", "above", "below", "is", "are", "a", "an", "its",
})


def extract_topic_tags(chapter_title: str) -> list[str]:
    """Return lower-cased, stop-word-freed tokens from a chapter title."""
    if not chapter_title or not isinstance(chapter_title, str):
        return []
    tokens = re.split(r"[\s\-_/]+", chapter_title.strip().lower())
    return [t for t in tokens if t and t not in _STOP_WORDS]


# ---------------------------------------------------------------------------
# Field parsing helpers (used by CSV-based cleaners)
# ---------------------------------------------------------------------------

def split_book(book: str) -> tuple[str, str]:
    """Split a ``"number | Title"`` book field into (book_number, book_title)."""
    if not book or str(book).strip().lower() in ("nan", "none", ""):
        return "", ""
    parts = str(book).split("|")
    return parts[0].strip(), parts[1].strip() if len(parts) > 1 else parts[0].strip()


def split_chapter(chapter: str) -> tuple[str, str]:
    """Split a ``"number | Title"`` chapter field into (chapter_number, chapter_title)."""
    if not chapter or str(chapter).strip().lower() in ("nan", "none", ""):
        return "", ""
    parts = str(chapter).split("|", 1)
    return parts[0].strip(), parts[1].strip() if len(parts) > 1 else ""


def extract_numeric(text: str) -> str:
    """Return the first sequence of digits found in *text*."""
    match = re.search(r"\d+", str(text))
    return match.group() if match else ""


def clean_text(text: str) -> str:
    """Strip a leading number + punctuation/whitespace prefix from *text*."""
    return re.sub(r"^\d+[\.\s]*", "", str(text)).strip()


def safe_int(x: object) -> int | float:
    """Return the int value of *x*, or ``float("inf")`` on failure."""
    try:
        return int(x)
    except (TypeError, ValueError):
        return float("inf")


def normalize_hadith_number(raw: str) -> str:
    """Extract just the number from various hadith-number formats.

    Handles ``"1"`` → ``"1"``, ``"Ḥadīth #1"`` → ``"1"``,
    ``"Passage #1"`` → ``"1"``, etc.
    """
    match = re.search(r"\d+", str(raw))
    return match.group() if match else str(raw).strip()
