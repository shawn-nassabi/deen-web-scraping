"""Cleaner for Nahj al-Balagha CSV.

Reads the single Nahj al-Balagha CSV, normalises columns, groups by chapter,
chunks with the shared paragraph-aware chunker, and writes JSONL.
"""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from deen_scraper.cleaners.base import (
    chunk_paragraphs,
    split_book,
    split_chapter,
    extract_numeric,
    clean_text,
    safe_int,
)
from deen_scraper.config import CHUNK_FILES, COLLECTIONS

INPUT_FILE = "data/raw/shia/nahjul_balagha/NahjalBalagha_ThePeakofEloquence__alSharifalRadi.csv"
OUTPUT_JSONL = CHUNK_FILES["nahjul-balagha"]


def build_chunks(row, base_chunk_idx):
    metadata = {
        "sect": COLLECTIONS["nahjul-balagha"]["sect"],
        "collection": "nahjul-balagha",
        "author": row["author"],
        "volume": "",
        "book_number": row["book_number"],
        "book_title": row["book_title"],
        "chapter_number": row["chapter_number"],
        "chapter_title": row["chapter_title"],
        "hadith_no": row["hadith_no"],
        "lang": "en",
        "grade_en": "",
        "grade_ar": "",
        "text_en": row["hadees_english"],
        "text_ar": row["hadees_arabic"],
    }
    chunks = chunk_paragraphs(row["hadees_english"])
    return [
        {**metadata, "chunk_id": f"nahjul_balagha_{base_chunk_idx + i}", "text_chunk": chunk}
        for i, chunk in enumerate(chunks)
    ]


def process_nahjul_balagha(input_file=INPUT_FILE):
    df = pd.read_csv(input_file)

    df["hadees_arabic"] = df["hadees_arabic"].astype(str).str.strip()
    df["hadees_english"] = df["hadees_english"].astype(str).str.strip()
    df = df[(df["hadees_arabic"] != "") & (df["hadees_english"] != "")]

    df["book_number"], df["book_title"] = zip(*df["book"].apply(split_book))
    df["chapter_number"], df["chapter_title"] = zip(*df["chapter"].apply(split_chapter))
    df["hadith_no"] = df["chapter_number"].apply(extract_numeric)
    df["chapter_number"] = df["chapter_number"].apply(extract_numeric)
    df["hadees_english"] = df["hadees_english"].apply(clean_text)
    df["hadees_arabic"] = df["hadees_arabic"].apply(clean_text)

    grouped = df.groupby([
        "book_number", "book_title", "chapter_number",
        "chapter_title", "hadith_no", "author",
    ]).agg({
        "hadees_english": lambda x: "\n\n".join(x),
        "hadees_arabic": lambda x: "\n\n".join(x),
    }).reset_index()

    grouped["book_int"] = grouped["book_number"].apply(safe_int)
    grouped["hadith_int"] = grouped["hadith_no"].apply(safe_int)
    grouped = grouped.sort_values(
        by=["book_int", "hadith_int"]
    ).drop(columns=["book_int", "hadith_int"])

    all_chunks = []
    global_chunk_idx = 0
    for _, row in grouped.iterrows():
        chunk_set = build_chunks(row, global_chunk_idx)
        all_chunks.extend(chunk_set)
        global_chunk_idx += len(chunk_set)

    Path(OUTPUT_JSONL).parent.mkdir(parents=True, exist_ok=True)
    df_chunks = pd.DataFrame(all_chunks)
    df_chunks.to_json(OUTPUT_JSONL, orient="records", lines=True)
    print(f"Done: {len(df_chunks)} chunks saved to:\n - {OUTPUT_JSONL}")
    return all_chunks


if __name__ == "__main__":
    process_nahjul_balagha()
