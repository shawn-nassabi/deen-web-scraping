"""Unified text chunking utilities.

Two strategies are available:
1. ``chunk_paragraphs`` from ``deen_scraper.cleaners.base`` — paragraph-aware
   grouping with word-level overlap (used for hadith collections).
2. ``split_recursive`` — wraps langchain's ``RecursiveCharacterTextSplitter``
   (used for long-form commentary like Al-Mizan Tafsir).

The ``chunk_text`` helper auto-selects based on whether the text contains
blank-line paragraph breaks or exceeds a word-count threshold.
"""

from __future__ import annotations

from deen_scraper.cleaners.base import chunk_paragraphs, CHUNK_SIZE, CHUNK_OVERLAP

try:
    from langchain_text_splitters import RecursiveCharacterTextSplitter
    _HAS_LANGCHAIN = True
except ImportError:
    _HAS_LANGCHAIN = False


def split_recursive(
    text: str,
    *,
    chunk_size: int = CHUNK_SIZE,
    chunk_overlap: int = CHUNK_OVERLAP,
    separators: list[str] | None = None,
) -> list[str]:
    """Chunk using langchain's RecursiveCharacterTextSplitter."""
    if not _HAS_LANGCHAIN:
        raise ImportError(
            "langchain / langchain-text-splitters is required for "
            "RecursiveCharacterTextSplitter.  Install with: "
            "pip install langchain langchain-text-splitters"
        )
    if separators is None:
        separators = ["\n\n", "\n", ".", " "]
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=separators,
    )
    return splitter.split_text(text)


def smart_chunk(
    text: str,
    *,
    chunk_size: int = CHUNK_SIZE,
    overlap: int = CHUNK_OVERLAP,
    word_threshold: int = 400,
    use_recursive: bool = False,
) -> list[str]:
    """Choose the best chunking strategy for *text*.

    - If ``use_recursive`` and langchain is available, always use
      ``RecursiveCharacterTextSplitter``.
    - If the text is longer than *word_threshold* words and has blank-line
      paragraph breaks, use paragraph-based chunking.
    - Otherwise fall back to a single-element list.
    """
    words = text.split()
    if len(words) <= 1:
        return [text] if text.strip() else []

    if use_recursive and _HAS_LANGCHAIN:
        return split_recursive(text, chunk_size=chunk_size, chunk_overlap=overlap)

    if len(words) > word_threshold and "\n\n" in text:
        return chunk_paragraphs(text, chunk_size=chunk_size, overlap=overlap)

    # Text is short enough to keep as-is
    return [text]
