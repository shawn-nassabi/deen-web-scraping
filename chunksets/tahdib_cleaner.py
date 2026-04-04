import pandas as pd
import re
import os
from pathlib import Path

# ---- Paths (self-resolving) ----
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)

INPUT_DIR = os.path.join(REPO_ROOT, "datasets", "tahdib-al-ahkam")
OUTPUT_DIR = os.path.join(REPO_ROOT, "datasets", "cleaned_data")
OUTPUT_JSONL = os.path.join(OUTPUT_DIR, "tahdib_al_ahkam_cleaned_chunks.jsonl")

CHUNK_SIZE = 350
CHUNK_OVERLAP = 50

COLLECTION_NAME = "tahdib-al-ahkam"
SECT = "shia"
AUTHOR = "Shaykh al-Tusi"

# Volume files to process (add more as they appear)
VOLUME_FILES = [
    "tahdib-al-ahkam-vol.1_hadiths.csv",
    "tahdib-al-ahkam-vol.2_hadiths.csv",
    "tahdib-al-ahkam-vol.3_hadiths.csv",
]

# ---- Helpers ----

def extract_volume_from_filename(filename: str) -> str:
    """Extract volume number from filenames like tahdib-al-ahkam-vol.1_hadiths.csv"""
    m = re.search(r"vol\.(\d+)", filename)
    return m.group(1) if m else ""


def chunk_paragraphs(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP):
    """Paragraph-aware chunking (same pattern as existing cleaners)."""
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks = []
    current = []
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


def extract_topic_tags(chapter_title: str) -> list:
    """Extract topic/fiqh-category tags from the chapter title."""
    if not chapter_title or not isinstance(chapter_title, str):
        return []
    # e.g. "CAUSES REQUIRING PURIFICATION" -> ["causes", "requiring", "purification"]
    tokens = re.split(r"[\s\-\_/]+", chapter_title.strip().lower())
    # Filter common stop words that don't add topic signal
    stopwords = {
        "the", "of", "and", "in", "on", "for", "to", "at", "by", "with",
        "from", "about", "between", "into", "through", "during", "before",
        "after", "above", "below", "is", "are", "a", "an", "its",
    }
    tags = [t for t in tokens if t and t not in stopwords]
    return tags


def build_chunks(row: dict) -> list:
    """Build chunked records for a single hadith row."""
    vol = row["volume"]
    chapter_num = str(row["chapter_number"]).strip()
    hadith_no = str(row["hadith_no"]).strip()

    hadith_id = f"{SECT}_{COLLECTION_NAME}_{vol}_{chapter_num}_{hadith_no}"

    # Clean field values (NaNs already turned to "" in main loop)
    def safe_str(key, default=""):
        v = row.get(key, default)
        if v is None:
            return default
        return str(v).strip() if v != "" else ""

    # Combine english_text + commentary as one English body
    english_body = safe_str("english_text")
    commentary = safe_str("commentary")

    if commentary:
        combined_en = f"{english_body}\n\nScholar's Note:\n{commentary}"
    else:
        combined_en = english_body

    text_ar = safe_str("arabic_text")
    chapter_title = safe_str("chapter_title")
    source_col = safe_str("source")
    references_col = safe_str("references")
    page_start = safe_str("page_start")
    page_end = safe_str("page_end")

    # Topic tags from chapter title
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

    # Chunk the combined English text
    chunks = chunk_paragraphs(combined_en)

    return [
        {
            **base_metadata,
            "chunk_id": f"tahdib_{vol}_{chapter_num}_{hadith_no}_{i}",
            "text_chunk": chunk,
        }
        for i, chunk in enumerate(chunks)
    ]


# ---- Main Processing ----

def process_tahdib():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    all_chunks = []

    for fname in VOLUME_FILES:
        fpath = os.path.join(INPUT_DIR, fname)
        if not os.path.exists(fpath):
            print(f"Warning: File not found: {fpath} -- skipping.")
            continue

        volume_num = extract_volume_from_filename(fname)
        print(f"Processing {fname} (volume {volume_num})...")

        df = pd.read_csv(fpath)

        # Normalize column names to match our uniform schema
        df = df.rename(columns={
            "Chapter Number": "chapter_number",
            "Chapter Title": "chapter_title",
            "Hadith Number": "hadith_no",
        })

        # Drop rows missing essential text
        df["english_text"] = df["english_text"].astype(str).str.strip()
        df["arabic_text"] = df["arabic_text"].astype(str).str.strip()
        df = df[(df["english_text"] != "") & (df["english_text"] != "nan")]

        # Assign volume column from filename
        df["volume"] = volume_num

        for _, row in df.iterrows():
            record = {}
            for k, v in row.to_dict().items():
                if pd.isna(v):
                    record[k] = ""
                else:
                    record[k] = v
            chunk_set = build_chunks(record)
            all_chunks.extend(chunk_set)

    # Save to JSONL
    df_chunks = pd.DataFrame(all_chunks)
    df_chunks.to_json(OUTPUT_JSONL, orient="records", lines=True, force_ascii=False)

    print(f"\nDone: {len(df_chunks)} chunks saved to:\n - {OUTPUT_JSONL}")


if __name__ == "__main__":
    process_tahdib()
