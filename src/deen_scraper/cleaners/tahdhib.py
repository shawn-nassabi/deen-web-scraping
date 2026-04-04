"""Cleaner for Tahdhib al-Ahkam CSV volumes.

Reads volume CSVs, normalises column names, combines english_text with
commentary, tags topics from chapter titles, chunks, and writes JSONL.
"""

from __future__ import annotations

import os

import pandas as pd

from deen_scraper.cleaners.base import chunk_paragraphs, extract_topic_tags
from deen_scraper.config import COLLECTION_INPUTS, CHUNK_FILES, COLLECTIONS

INPUT_DIR = COLLECTION_INPUTS["tahdhib-al-ahkam"]
OUTPUT_JSONL = CHUNK_FILES["tahdhib-al-ahkam"]

COLLECTION_NAME = "tahdhib-al-ahkam"
SECT = "shia"
AUTHOR = "Shaykh al-Tusi"

VOLUME_FILES = [
    "tahdhib-al-ahkam-vol.1_hadiths.csv",
    "tahdhib-al-ahkam-vol.2_hadiths.csv",
    "tahdhib-al-ahkam-vol.3_hadiths.csv",
]


def extract_volume_from_filename(filename: str) -> str:
    """Extract volume number from filenames like tahdhib-al-ahkam-vol.1_hadiths.csv."""
    import re
    m = re.search(r"vol\.(\d+)", filename)
    return m.group(1) if m else ""


def build_chunks(row: dict) -> list:
    """Build chunked records for a single hadith row."""
    vol = row["volume"]
    chapter_num = str(row["chapter_number"]).strip()
    hadith_no = str(row["hadith_no"]).strip()

    hadith_id = f"{SECT}_{COLLECTION_NAME}_{vol}_{chapter_num}_{hadith_no}"

    def safe_str(key, default=""):
        v = row.get(key, default)
        if v is None:
            return default
        return str(v).strip() if v != "" else ""

    english_body = safe_str("english_text")
    commentary = safe_str("commentary")
    combined_en = f"{english_body}\n\nScholar\'s Note:\n{commentary}" if commentary else english_body

    text_ar = safe_str("arabic_text")
    chapter_title = safe_str("chapter_title")
    source_col = safe_str("source")
    references_col = safe_str("references")
    page_start = safe_str("page_start")
    page_end = safe_str("page_end")
    topic_tags = extract_topic_tags(chapter_title)

    base_metadata = {
        "sect": SECT,
        "collection": COLLECTION_NAME,
        "author": AUTHOR,
        "volume": vol,
        "book_number": "",
        "book_title": "",
        "chapter_number": chapter_num,
        "chapter_title": chapter_title,
        "hadith_no": hadith_no,
        "lang": "en",
        "grade_en": "",
        "grade_ar": "",
        "text_en": combined_en,
        "text_ar": text_ar,
        "commentary": commentary,
        "cross_references": references_col,
        "source_scholar": source_col,
        "page_start": page_start,
        "page_end": page_end,
        "topic_tags": topic_tags,
        "hadith_id": hadith_id,
    }

    chunks = chunk_paragraphs(combined_en)
    return [
        {
            **base_metadata,
            "chunk_id": f"tahdib_{vol}_{chapter_num}_{hadith_no}_{i}",
            "text_chunk": chunk,
        }
        for i, chunk in enumerate(chunks)
    ]


def process_tahdhib():
    """Process all Tahdhib volume CSVs into one JSONL file."""
    os.makedirs(os.path.dirname(OUTPUT_JSONL), exist_ok=True)
    all_chunks = []

    for fname in VOLUME_FILES:
        fpath = os.path.join(INPUT_DIR, fname)
        if not os.path.exists(fpath):
            print(f"Warning: File not found: {fpath} -- skipping.")
            continue

        volume_num = extract_volume_from_filename(fname)
        print(f"Processing {fname} (volume {volume_num})...")

        df = pd.read_csv(fpath)
        df = df.rename(columns={
            "Chapter Number": "chapter_number",
            "Chapter Title": "chapter_title",
            "Hadith Number": "hadith_no",
        })

        df["english_text"] = df["english_text"].astype(str).str.strip()
        df["arabic_text"] = df["arabic_text"].astype(str).str.strip()
        df = df[(df["english_text"] != "") & (df["english_text"] != "nan")]
        df["volume"] = volume_num

        for _, row in df.iterrows():
            record = {}
            for k, v in row.to_dict().items():
                record[k] = "" if pd.isna(v) else v
            chunk_set = build_chunks(record)
            all_chunks.extend(chunk_set)

    df_chunks = pd.DataFrame(all_chunks)
    df_chunks.to_json(OUTPUT_JSONL, orient="records", lines=True, force_ascii=False)
    print(f"\nDone: {len(df_chunks)} chunks saved to:\n - {OUTPUT_JSONL}")


if __name__ == "__main__":
    process_tahdhib()
