"""Cleaner for al-islam.org author collections.

Reads the ``chapters.jsonl`` produced by
``deen_scraper.scrapers.al_islam`` and emits canonical chunk records, one
JSONL file per author.  Every chunk is tagged with ``sect: shia``, the author's
display name, and the book title it came from.

Chapters are long-form prose, so chunking uses the paragraph-aware splitter
shared with the hadith cleaners: paragraph boundaries are respected and
adjacent chunks overlap, which keeps arguments that run across paragraphs
intact.

    python -m deen_scraper.cleaners.al_islam --author-slug murtadha-mutahhari
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from deen_scraper.chunking.splitter import split_recursive
from deen_scraper.cleaners.base import (
    CHUNK_OVERLAP,
    CHUNK_SIZE,
    chunk_paragraphs,
    extract_topic_tags,
)
from deen_scraper.config import (
    AL_ISLAM_AUTHORS,
    CHUNK_FILES,
    COLLECTION_INPUTS,
    COLLECTIONS,
    al_islam_collection_name,
)

SECT = "shia"

# Chapters below this length are almost always front matter (a dedication, a
# "translator's note" stub) rather than content worth embedding.
MIN_CHAPTER_WORDS = 10

# Runs of three or more consecutive Arabic words.  These books are English
# translations that quote the Arabic of Qur'an verses and hadith inline; the
# quotes are lifted into `text_ar` so the field carries the Arabic source the
# way it does for the hadith collections.
ARABIC_RUN_RE = re.compile(
    r"(?:[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]+"
    r"[\s\u060C\u061B\u061F]+){2,}"
    r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]+"
)


def extract_arabic_quotes(text: str) -> str:
    """Return the Arabic passages quoted inside *text*, one per line."""
    quotes = [match.group().strip() for match in ARABIC_RUN_RE.finditer(text)]
    return "\n".join(q for q in quotes if q)


# A chunk longer than this is split again.  The paragraph-aware splitter can
# only break between paragraphs, so a single very long paragraph comes back as
# one oversized chunk -- and all-mpnet-base-v2 silently truncates anything past
# roughly 384 tokens, which would drop the tail of that chunk from the vector.
MAX_CHUNK_WORDS = int(CHUNK_SIZE * 1.3)

# RecursiveCharacterTextSplitter measures in characters, not words, so the word
# budgets above are converted at roughly six characters per English word.
_CHARS_PER_WORD = 6


def chunk_chapter(text: str) -> list[str]:
    """Chunk chapter *text*, splitting any paragraph too long to embed."""
    chunks: list[str] = []
    for chunk in chunk_paragraphs(text):
        if len(chunk.split()) <= MAX_CHUNK_WORDS:
            chunks.append(chunk)
            continue
        chunks.extend(
            part
            for part in split_recursive(
                chunk,
                chunk_size=CHUNK_SIZE * _CHARS_PER_WORD,
                chunk_overlap=CHUNK_OVERLAP * _CHARS_PER_WORD,
            )
            if part.strip()
        )
    return chunks


def load_chapters(raw_path: Path) -> list[dict]:
    """Load scraped chapter records from a JSONL file."""
    records: list[dict] = []
    with raw_path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def build_topic_tags(chapter_title: str, book_tags: list[str]) -> list[str]:
    """Combine tokens from the chapter title with the book's site topics."""
    tags = extract_topic_tags(chapter_title)
    for tag in book_tags:
        token = tag.strip().lower()
        if token and token not in tags:
            tags.append(token)
    return tags


def build_chunks(record: dict, collection_name: str, author_name: str) -> list[dict]:
    """Turn one scraped chapter into a list of canonical chunk records."""
    text = (record.get("text") or "").strip()
    if len(text.split()) < MIN_CHAPTER_WORDS:
        return []

    book_slug = record.get("book_slug", "")
    book_title = record.get("book_title", "")
    chapter_order = str(record.get("chapter_order", ""))
    chapter_title = record.get("chapter_title", "") or ""

    def join(values) -> str:
        if isinstance(values, list):
            return ", ".join(str(v) for v in values if v)
        return str(values or "")

    unit_id = f"{SECT}_{collection_name}_{book_slug}_{chapter_order}"
    base = {
        "sect": SECT,
        "collection": collection_name,
        "author": author_name,
        "volume": "",
        "book_number": "",
        "book_title": book_title,
        "chapter_number": chapter_order,
        "chapter_title": chapter_title,
        "hadith_no": "",
        "lang": "en",
        "grade_en": "",
        "grade_ar": "",
        "commentary": "",
        # Footnotes are the closest thing these books have to a reference list.
        "cross_references": (record.get("footnotes") or "")[:2000],
        "source_scholar": "",
        "page_start": "",
        "page_end": "",
        "topic_tags": build_topic_tags(chapter_title, record.get("book_tags") or []),
        "hadith_id": unit_id,
        # al-islam.org specific provenance
        "source": "al-islam.org",
        "source_url": record.get("chapter_url", ""),
        "book_slug": book_slug,
        "book_url": record.get("book_url", ""),
        "chapter_slug": record.get("chapter_slug", ""),
        "translator": join(record.get("book_translators")),
        "publisher": join(record.get("book_publishers")),
    }

    chunks = chunk_chapter(text)
    return [
        {
            **base,
            "chunk_id": f"al-islam_{book_slug}_{chapter_order}_{i}",
            # text_en mirrors the chunk so Pinecone metadata stays small; the
            # full chapter is always recoverable from source_url.
            "text_en": chunk,
            # Arabic quotations stay inline in text_chunk so a retrieved
            # passage still reads as written, and are mirrored here so the
            # Arabic is queryable on its own.
            "text_ar": extract_arabic_quotes(chunk),
            "text_chunk": chunk,
        }
        for i, chunk in enumerate(chunks)
    ]


def process_author(author_slug: str) -> Path | None:
    """Clean and chunk one al-islam.org author collection."""
    collection_name = al_islam_collection_name(author_slug)
    if collection_name not in COLLECTIONS:
        raise ValueError(
            f"'{author_slug}' is not registered.  Add it to AL_ISLAM_AUTHORS in config.py."
        )

    raw_path = Path(COLLECTION_INPUTS[collection_name]) / "chapters.jsonl"
    if not raw_path.exists():
        print(f"No scraped data at {raw_path} -- run the scraper first.")
        return None

    output_path = Path(CHUNK_FILES[collection_name])
    output_path.parent.mkdir(parents=True, exist_ok=True)

    author_name = COLLECTIONS[collection_name]["author"]
    chapters = load_chapters(raw_path)
    print(f"Processing {len(chapters)} chapter(s) for {author_name} ...")

    all_chunks: list[dict] = []
    skipped = 0
    seen_ids: set[str] = set()
    for record in chapters:
        chunks = build_chunks(record, collection_name, author_name)
        if not chunks:
            skipped += 1
            continue
        for chunk in chunks:
            # Two books can share a chapter slug; keep chunk_id unique so the
            # Pinecone upsert cannot silently overwrite a different chunk.
            chunk_id = chunk["chunk_id"]
            if chunk_id in seen_ids:
                suffix = 2
                while f"{chunk_id}_{suffix}" in seen_ids:
                    suffix += 1
                chunk_id = f"{chunk_id}_{suffix}"
                chunk["chunk_id"] = chunk_id
            seen_ids.add(chunk_id)
            all_chunks.append(chunk)

    with output_path.open("w", encoding="utf-8") as sink:
        for chunk in all_chunks:
            sink.write(json.dumps(chunk, ensure_ascii=False) + "\n")

    books = {c["book_title"] for c in all_chunks}
    print(
        f"Done: {len(all_chunks)} chunks from {len(books)} book(s)"
        f"{f', {skipped} chapter(s) skipped as too short' if skipped else ''}\n"
        f"  {output_path}"
    )
    return output_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Clean and chunk al-islam.org author collections.")
    parser.add_argument(
        "--author-slug",
        default=None,
        choices=sorted(AL_ISLAM_AUTHORS),
        help="Author to clean (default: every registered author)",
    )
    args = parser.parse_args(argv)

    slugs = [args.author_slug] if args.author_slug else sorted(AL_ISLAM_AUTHORS)
    for slug in slugs:
        process_author(slug)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
