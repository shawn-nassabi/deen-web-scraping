"""Cleaner for Al-Kafi hadith CSV volumes.

Reads one CSV per volume from the raw data directory, normalises columns,
groups by chapter, chunks each hadith with the shared paragraph-aware
chunker, and writes a JSONL file to ``data/chunks/``.
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
    CHUNK_SIZE,
    CHUNK_OVERLAP,
)
from deen_scraper.config import (
    COLLECTION_INPUTS,
    CHUNK_FILES,
    COLLECTIONS,
)

INPUT_DIR = COLLECTION_INPUTS["alkafi"]
OUTPUT_JSONL = CHUNK_FILES["alkafi"]


def build_chunks(row, base_chunk_idx):
    """Build chunk records for one grouped hadith row."""
    metadata = {
        "sect": COLLECTIONS["alkafi"]["sect"],
        "collection": "alkafi",
        "author": row["author"],
        "volume": row["volume"],
        "book_number": row["book_number"],
        "book_title": row["book_title"],
        "chapter_title": row["chapter_title"],
        "chapter_number": row["chapter_number"],
        "hadith_no": row["hadith_no"],
        "lang": "en",
        "grade_en": row["grade_en"] if pd.notna(row["grade_en"]) else "",
        "grade_ar": "",
        "text_en": row["hadees_english"],
        "text_ar": row["hadees_arabic"],
    }

    chunks = chunk_paragraphs(row["hadees_english"])
    return [
        {**metadata, "chunk_id": f"alkafi_{base_chunk_idx + i}", "text_chunk": chunk}
        for i, chunk in enumerate(chunks)
    ]


def process_alkafi_folder(input_dir=INPUT_DIR):
    """Main processing pipeline for all Al-Kafi volume CSVs."""
    all_chunks = []
    files = sorted(Path(input_dir).glob("*.csv"))
    global_chunk_idx = 0

    for file in files:
        print(f"Processing {file.name}...")
        df = pd.read_csv(file)

        # Drop empty hadiths
        df["hadees_arabic"] = df["hadees_arabic"].astype(str).str.strip()
        df["hadees_english"] = df["hadees_english"].astype(str).str.strip()
        df = df[(df["hadees_arabic"] != "") & (df["hadees_english"] != "")]

        # Metadata extraction from filename
        vol_match = re.search(r"Volume(\d+)", file.name)
        df["volume"] = vol_match.group(1) if vol_match else ""
        df["book_number"], df["book_title"] = zip(*df["book"].apply(split_book))
        df["chapter_number"], df["chapter_title"] = zip(*df["chapter"].apply(split_chapter))
        df["chapter_number"] = df["chapter_number"].apply(extract_numeric)
        df["hadith_no"] = df["hadees_number"].apply(extract_numeric)
        df["hadees_english"] = df["hadees_english"].apply(clean_text)
        df["hadees_arabic"] = df["hadees_arabic"].apply(clean_text)
        df["collection"] = "alkafi"
        df["lang"] = "en"
        if "grade_en" not in df.columns:
            df["grade_en"] = ""

        # Group by chapter (each hadith)
        grouped = df.groupby([
            "volume", "book_number", "book_title",
            "chapter_number", "chapter_title",
            "hadith_no", "author", "grade_en",
        ]).agg({
            "hadees_english": lambda x: "\n\n".join(x),
            "hadees_arabic": lambda x: "\n\n".join(x),
        }).reset_index()

        # Sort naturally
        grouped["volume_int"] = grouped["volume"].apply(safe_int)
        grouped["book_int"] = grouped["book_number"].apply(safe_int)
        grouped["hadith_int"] = grouped["hadith_no"].apply(safe_int)
        grouped = grouped.sort_values(
            by=["volume_int", "book_int", "hadith_int"]
        ).drop(columns=["volume_int", "book_int", "hadith_int"])

        for _, row in grouped.iterrows():
            chunk_set = build_chunks(row, global_chunk_idx)
            all_chunks.extend(chunk_set)
            global_chunk_idx += len(chunk_set)

    # Save
    Path(OUTPUT_JSONL).parent.mkdir(parents=True, exist_ok=True)
    df_chunks = pd.DataFrame(all_chunks)
    df_chunks.to_json(OUTPUT_JSONL, orient="records", lines=True)
    print(f"Done: {len(df_chunks)} chunks saved to:\n - {OUTPUT_JSONL}")
    return all_chunks


if __name__ == "__main__":
    process_alkafi_folder()
