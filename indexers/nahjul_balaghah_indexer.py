import pandas as pd
import re
from langchain.text_splitter import RecursiveCharacterTextSplitter

# Input/output
INPUT_FILE = "../datasets/nahjulbalaghah/NahjalBalagha_ThePeakofEloquence__alSharifalRadi.csv"
OUTPUT_CSV = "../chunksets/nahjul_balagha_cleaned_chunks.csv"
OUTPUT_JSONL = "../chunksets/nahjul_balagha_cleaned_chunks.jsonl"
# Config
CHUNK_SIZE = 350
CHUNK_OVERLAP = 50

# Helpers
def split_book(book):
    parts = str(book).split("|")
    return parts[0].strip(), parts[1].strip() if len(parts) > 1 else parts[0].strip()

def split_chapter(chapter):
    parts = str(chapter).split("|")
    return parts[0].strip(), parts[1].strip() if len(parts) > 1 else chapter.strip()

def extract_chapter_number(chapter_str):
    match = re.search(r'\d+', str(chapter_str))
    return match.group() if match else ""

def chunk_paragraphs(text, chunk_size=CHUNK_SIZE, overlap=CHUNK_OVERLAP):
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks = []
    current = []
    current_len = 0

    for p in paragraphs:
        p_len = len(p.split())
        if current_len + p_len > chunk_size and current:
            chunks.append(" ".join(current))
            # Add overlap
            overlap_words = " ".join(" ".join(current).split()[-overlap:])
            current = [overlap_words, p]
            current_len = len(overlap_words.split()) + p_len
        else:
            current.append(p)
            current_len += p_len

    if current:
        chunks.append(" ".join(current))
    return chunks

def build_chunks(row):
    metadata = {
        "sect": "shia",
        "collection": "nahjul-balagha",
        "author": "Imam Ali ibn Abu Talib",
        "volume": "",
        "book_number": row["book_number"],
        "book_title": row["book_title"],
        "chapter_title": row["chapter_title"],
        "hadith_no": row["hadith_no"],
        "lang": "en",
        "grade_en": "",
        "grade_ar": "",
        "text_ar": row["hadees_arabic"]
    }

    chunks = chunk_paragraphs(row["hadees_english"])
    return [{**metadata, "chunk_id": str(i), "text_en": chunk} for i, chunk in enumerate(chunks)]

# Pipeline
def consolidate_and_chunk(input_file):
    df = pd.read_csv(input_file)

    # Clean
    df["hadees_arabic"] = df["hadees_arabic"].astype(str).str.strip()
    df["hadees_english"] = df["hadees_english"].astype(str).str.strip()
    df = df[(df["hadees_arabic"] != "") & (df["hadees_english"] != "")]

    # Extract metadata
    df["book_number"], df["book_title"] = zip(*df["book"].apply(split_book))
    df["chapter_number"], df["chapter_title"] = zip(*df["chapter"].apply(split_chapter))
    df["hadith_no"] = df["chapter_number"].apply(extract_chapter_number)
    df["collection"] = "nahjul-balagha"

    # Group per chapter
    grouped = df.groupby([
        "book_number", "book_title", "chapter_number", "chapter_title", "hadith_no", "author", "collection"
    ]).agg({
        "hadees_english": lambda x: "\n\n".join(x),
        "hadees_arabic": lambda x: "\n\n".join(x)
    }).reset_index()

    # Sort numerically
    grouped["sort_key"] = grouped["hadith_no"].apply(lambda x: int(x) if x.isdigit() else float('inf'))
    grouped = grouped.sort_values(by=["book_number", "sort_key"]).drop(columns=["sort_key"])

    # Chunk it
    all_chunks = []
    for _, row in grouped.iterrows():
        all_chunks.extend(build_chunks(row))

    # Output
    df_chunks = pd.DataFrame(all_chunks)
    df_chunks.to_csv(OUTPUT_CSV, index=False)
    df_chunks.to_json(OUTPUT_JSONL, orient="records", lines=True)
    print(f"✅ {len(df_chunks)} chunks saved:\n - {OUTPUT_CSV}\n - {OUTPUT_JSONL}")

# Run it
if __name__ == "__main__":
    consolidate_and_chunk(INPUT_FILE)