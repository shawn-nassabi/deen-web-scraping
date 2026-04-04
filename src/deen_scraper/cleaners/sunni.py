"""Unified cleaner for all five Sunni hadith collections.

Replaces the hardcoded calls that were duplicated in both ``index_dense.py``
and ``index_sparse.py``.  Provide a collection name and CSV path and get
back chunk records ready for embedding.
"""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from deen_scraper.chunking.splitter import split_recursive
from deen_scraper.config import SUNNI_COLLECTIONS, COLLECTIONS

# Mapping from collection key to raw CSV base name (without directory)
SUNNI_CSV_MAP = {
    "sahih-bukhari":  "Sahih_al-Bukhari_all_books.csv",
    "sahih-muslim":   "Sahih_Muslim_8b_all_books.csv",
    "tirmidhi":       "Jami`_at-Tirmidhi_all_books.csv",
    "abu-dawood":     "Sunan_Abi_Dawud_all_books.csv",
    "an-nasai":       "Sunan_an-Nasa'i_all_books.csv",
}


def process_sunni_csv(csv_path, collection_name, sect="sunni"):
    """Process one Sunni collection CSV into chunk records."""
    df = pd.read_csv(csv_path)

    # Drop rows with missing data
    df.dropna(subset=["english", "arabic"], inplace=True)

    entries = []
    chunk_counter = 0

    for _, row in df.iterrows():
        book_raw = row.get("book", "")
        chapter_raw = row.get("in_book_reference", "")
        grade_en = str(row.get("english_grade", "")).strip() or ""
        grade_ar = str(row.get("arabic_grade", "")).strip() or ""
        reference = row.get("reference", "").strip() or ""
        hadith_url = row.get("hadith_url", "").strip() or ""

        # Parse book number and title
        match = re.match(r"\s*(\d+)[\.\:\-\)]?\s*(.+)?", book_raw)
        book_number, book_title = "", ""
        if match:
            book_number = match.group(1)
            book_title = match.group(2) or ""

        # Parse Chapter/Hadith Number
        hadith_no = ""
        match2 = re.match(r"Book\s*(\d+)\s*,\s*Hadith\s*(\d+)", chapter_raw)
        if match2:
            book_number = match2.group(1)
            hadith_no = match2.group(2)

        # Clean texts
        text_en_full = row["english"]
        text_ar_full = row["arabic"]

        # Determine hadith ID
        hadith_id = f"{sect}_{collection_name}_{book_number}_{hadith_no}"

        # Apply chunking
        if len(text_en_full.split()) > 400:
            chunks = split_recursive(text_en_full)
        else:
            chunks = [text_en_full]

        for i, chunk in enumerate(chunks):
            metadata = {
                "sect": sect,
                "collection": collection_name,
                "author": COLLECTIONS.get(collection_name, {}).get("author", ""),
                "volume": "",
                "book_number": book_number,
                "book_title": book_title,
                "chapter_title": "",
                "chapter_number": hadith_no,
                "hadith_no": hadith_no,
                "lang": "en",
                "chunk_id": f"{collection_name}_{chunk_counter}",
                "grade_en": grade_en,
                "grade_ar": grade_ar,
                "text_en": text_en_full,
                "text_ar": text_ar_full,
                "reference": reference,
                "hadith_url": hadith_url,
                "hadith_id": hadith_id,
                "text_chunk": chunk,
            }
            entries.append(metadata)
            chunk_counter += 1

    return entries


def process_all_sunni(sunni_csv_dir="data/raw/sunni"):
    """Process all five Sunni collections from the raw CSV directory."""
    results = {}
    for coll_key in SUNNI_COLLECTIONS:
        csv_name = SUNNI_CSV_MAP[coll_key]
        csv_path = Path(sunni_csv_dir) / csv_name
        if not csv_path.exists():
            print(f"Warning: {csv_path} not found, skipping {coll_key}.")
            continue
        chunks = process_sunni_csv(str(csv_path), coll_key)
        results[coll_key] = chunks
        print(f"  Processed {len(chunks)} {coll_key} chunks.")
    return results


if __name__ == "__main__":
    results = process_all_sunni()
    for k, v in results.items():
        print(f"Processed {len(v)} {k} chunks.")
