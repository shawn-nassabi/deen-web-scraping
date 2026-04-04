"""Central configuration for the Deen Scraper project.

All paths are resolved relative to this file so every script
gets the same constants without sys.path hacks or absolute paths.
"""

from __future__ import annotations

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Project root & data directories
# ---------------------------------------------------------------------------
ROOT_DIR = Path(__file__).resolve().parents[2]  # deen-web-scraping/
DATA_DIR = ROOT_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
CHUNKS_DIR = DATA_DIR / "chunks"

# ── Raw data sub-paths ──────────────────────────────────────────────────
SHIA_RAW = RAW_DIR / "shia"
SUNNI_RAW = RAW_DIR / "sunni"

COLLECTION_INPUTS = {
    "alkafi":               SHIA_RAW / "alkafi",
    "nahjul-balagha":       SHIA_RAW / "nahjul_balagha",
    "man-la-yahduruhu-al-faqih": SHIA_RAW / "man-la-yahduruhu-al-faqih" / "csv",
    "tahdhib-al-ahkam":     SHIA_RAW / "tahdhib-al-ahkam" / "csv",
    "al-mizan":             SHIA_RAW / "al-mizan",
}

# ── PDF paths ───────────────────────────────────────────────────────────
FAQIH_PDF_DIR = SHIA_RAW / "man-la-yahduruhu-al-faqih" / "pdfs"
TAHDHIB_PDF_DIR = SHIA_RAW / "tahdhib-al-ahkam" / "pdfs"
AL_MIZAN_PDF_DIR = SHIA_RAW / "al-mizan" / "pdfs"
AL_MIZAN_SVG_DIR = SHIA_RAW / "al-mizan" / "svg_scraped"

# ── Chunked output files ───────────────────────────────────────────────
CHUNK_FILES = {
    "alkafi":               CHUNKS_DIR / "alkafi_cleaned_chunks.jsonl",
    "nahjul-balagha":       CHUNKS_DIR / "nahjul_balagha_cleaned_chunks.jsonl",
    "man-la-yahduruhu-al-faqih": CHUNKS_DIR / "faqih_cleaned_chunks.jsonl",
    "tahdhib-al-ahkam":     CHUNKS_DIR / "tahdhib_al_ahkam_cleaned_chunks.jsonl",
    "al-mizan":             CHUNKS_DIR / "al_mizan_cleaned_chunks.jsonl",
}

# ---------------------------------------------------------------------------
# Pipeline defaults (can be overridden by .env)
# ---------------------------------------------------------------------------
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "350"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "50"))

# ── Pinecone / Embedding ────────────────────────────────────────────────
EMBEDDING_MODEL = os.getenv(
    "EMBEDDING_MODEL", "sentence-transformers/all-mpnet-base-v2"
)
DENSE_INDEX_NAME = os.getenv("DENSE_INDEX_NAME", "deen-index-v2")
SPARSE_INDEX_NAME = os.getenv("SPARSE_INDEX_NAME", "deen-index-v2-sparse")
PINECONE_NAMESPACE = os.getenv("PINECONE_NAMESPACE", "ns1")
INDEX_BATCH_SIZE = int(os.getenv("PINECONE_BATCH_SIZE", "50"))

DENSE_RESULT_WEIGHT = float(os.getenv("DENSE_RESULT_WEIGHT", "0.7"))
SPARSE_RESULT_WEIGHT = float(os.getenv("SPARSE_RESULT_WEIGHT", "0.3"))
REFERENCE_FETCH_COUNT = int(os.getenv("REFERENCE_FETCH_COUNT", "10"))

# ---------------------------------------------------------------------------
# Collection metadata registry
# ---------------------------------------------------------------------------
COLLECTIONS: dict[str, dict] = {
    # ── Shia collections ──────────────────────────────────────────────
    "alkafi": {
        "sect": "shia",
        "author": "Shaykh Muhammad b. Ya'qub al-Kulayni",
        "indexer_prompt": (
            "Collection: Al-Kafi\n"
            "Author: {author}\n"
            "Volume: {volume}\nBook: {book_title}\n"
            "Chapter No: {chapter_number}\n"
            "Chapter Title: {chapter_title}\n"
            "Hadith No: {hadith_no}\n"
            "Grade: {grade_en}\n{text_chunk}"
        ),
    },
    "nahjul-balagha": {
        "sect": "shia",
        "author": "al-Sharif al-Radi",
        "indexer_prompt": (
            "Collection: Nahj al-Balagha\n"
            "Author: {author}\n"
            "Book: {book_title}\n"
            "Chapter No: {chapter_number}\n"
            "Chapter Title: {chapter_title}\n"
            "Sermon No: {hadith_no}\n{text_chunk}"
        ),
    },
    "man-la-yahduruhu-al-faqih": {
        "sect": "shia",
        "author": "Shaykh al-Saduq",
        "indexer_prompt": (
            "Collection: Man La Yahduruhu al-Faqih\n"
            "Author: {author}\n"
            "Volume: {volume}\n"
            "Chapter No: {chapter_number}\n"
            "Chapter Title: {chapter_title}\n"
            "Hadith No: {hadith_no}\n"
            "Source: {source_scholar}\n"
            "Page: {page_start}-{page_end}\n"
            "Topic Tags: {topic_tags}\n{text_chunk}"
        ),
    },
    "tahdhib-al-ahkam": {
        "sect": "shia",
        "author": "Shaykh al-Tusi",
        "indexer_prompt": (
            "Collection: Tahdhib al-Ahkam\n"
            "Author: {author}\n"
            "Volume: {volume}\n"
            "Chapter No: {chapter_number}\n"
            "Chapter Title: {chapter_title}\n"
            "Hadith No: {hadith_no}\n"
            "Source: {source_scholar}\n"
            "Page: {page_start}-{page_end}\n"
            "Topic Tags: {topic_tags}\n{text_chunk}"
        ),
    },
    "al-mizan": {
        "sect": "shia",
        "author": "Allamah Sayyid Muhammad Husayn Tabatabai",
        "indexer_prompt": (
            "Collection: Al-Mizan Tafsir\n"
            "Title: {title}\n"
            "Volume: {volume}\n"
            "Chapters: {chapters}\n"
            "Verses: {verses}\n"
            "Verse Reference: {verse_reference}\n"
            "Translator: {translator}\n{text_chunk}"
        ),
    },
    # ── Sunni collections ─────────────────────────────────────────────
    "sahih-bukhari": {
        "sect": "sunni",
        "author": "Imam Muhammad al-Bukhari",
        "indexer_prompt": (
            "Collection: Sahih al-Bukhari\n"
            "Book No: {book_number}\n"
            "Book Title: {book_title}\n"
            "Hadith No: {hadith_no}\n"
            "Grade: {grade_en}\n"
            "Reference: {reference}\n{text_chunk}"
        ),
    },
    "sahih-muslim": {
        "sect": "sunni",
        "author": "Imam Muslim ibn al-Hajjaj",
        "indexer_prompt": (
            "Collection: Sahih Muslim\n"
            "Book No: {book_number}\n"
            "Book Title: {book_title}\n"
            "Hadith No: {hadith_no}\n"
            "Grade: {grade_en}\n"
            "Reference: {reference}\n{text_chunk}"
        ),
    },
    "tirmidhi": {
        "sect": "sunni",
        "author": "Imam at-Tirmidhi",
        "indexer_prompt": (
            "Collection: Jami' at-Tirmidhi\n"
            "Book No: {book_number}\n"
            "Book Title: {book_title}\n"
            "Hadith No: {hadith_no}\n"
            "Grade: {grade_en}\n"
            "Reference: {reference}\n{text_chunk}"
        ),
    },
    "abu-dawood": {
        "sect": "sunni",
        "author": "Imam Abu Dawud",
        "indexer_prompt": (
            "Collection: Sunan Abi Dawud\n"
            "Book No: {book_number}\n"
            "Book Title: {book_title}\n"
            "Hadith No: {hadith_no}\n"
            "Grade: {grade_en}\n"
            "Reference: {reference}\n{text_chunk}"
        ),
    },
    "an-nasai": {
        "sect": "sunni",
        "author": "Imam an-Nasa'i",
        "indexer_prompt": (
            "Collection: Sunan an-Nasa'i\n"
            "Book No: {book_number}\n"
            "Book Title: {book_title}\n"
            "Hadith No: {hadith_no}\n"
            "Grade: {grade_en}\n"
            "Reference: {reference}\n{text_chunk}"
        ),
    },
}

SUNNI_COLLECTIONS = [
    "sahih-bukhari", "sahih-muslim", "tirmidhi", "abu-dawood", "an-nasai"
]
