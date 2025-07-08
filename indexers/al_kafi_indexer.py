import pandas as pd
import re
from pathlib import Path

INPUT_DIR = "../datasets/alkafi"
OUTPUT_CSV = "../chunksets/alkafi_cleaned_chunks.csv"
OUTPUT_JSONL = "../chunksets/alkafi_cleaned_chunks.jsonl"
CHUNK_SIZE = 350
CHUNK_OVERLAP = 50

# Helpers
def chunk_paragraphs(text, chunk_size=CHUNK_SIZE, overlap=CHUNK_OVERLAP):
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

def split_book(book):
    parts = str(book).split("|")
    return parts[0].strip(), parts[1].strip() if len(parts) > 1 else parts[0].strip()

def split_chapter(chapter):
    parts = str(chapter).split("|", 1)
    return parts[0].strip(), parts[1].strip() if len(parts) > 1 else ""

def extract_numeric(text):
    match = re.search(r"\d+", str(text))
    return match.group() if match else ""

def clean_text(text):
    return re.sub(r"^\d+[\.\s]*", "", str(text)).strip()

def safe_int(x):
    try:
        return int(x)
    except:
        return float("inf")

def build_chunks(row, base_chunk_idx):
    metadata = {
        "sect": "shia",
        "collection": "al-kafi",
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
        "text_ar": row["hadees_arabic"]
    }

    chunks = chunk_paragraphs(row["hadees_english"])
    return [
        {**metadata, "chunk_id": f"alkafi_{base_chunk_idx + i}", "text_chunk": chunk}
        for i, chunk in enumerate(chunks)
    ]

# Main Processing Pipeline
def process_alkafi_folder(input_dir):
    all_chunks = []
    files = list(Path(input_dir).glob("*.csv"))
    global_chunk_idx = 0

    for file in sorted(files):
        print(f"📖 Processing {file.name}...")
        df = pd.read_csv(file)

        # Clean empty
        df["hadees_arabic"] = df["hadees_arabic"].astype(str).str.strip()
        df["hadees_english"] = df["hadees_english"].astype(str).str.strip()
        df = df[(df["hadees_arabic"] != "") & (df["hadees_english"] != "")]

        # Metadata cleaning
        df["volume"] = re.search(r"Volume(\d+)", file.name).group(1) if re.search(r"Volume(\d+)", file.name) else ""
        df["book_number"], df["book_title"] = zip(*df["book"].apply(split_book))
        df["chapter_number"], df["chapter_title"] = zip(*df["chapter"].apply(split_chapter))
        df["chapter_number"] = df["chapter_number"].apply(extract_numeric)
        df["hadith_no"] = df["hadees_number"].apply(extract_numeric)
        df["hadees_english"] = df["hadees_english"].apply(clean_text)
        df["hadees_arabic"] = df["hadees_arabic"].apply(clean_text)
        df["collection"] = "al-kafi"
        df["lang"] = "en"
        if "grade_en" not in df.columns:
            df["grade_en"] = ""

        # Group by chapter (each hadith)
        grouped = df.groupby([
            "volume", "book_number", "book_title", "chapter_number", "chapter_title", "hadith_no", "author", "grade_en"
        ]).agg({
            "hadees_english": lambda x: "\n\n".join(x),
            "hadees_arabic": lambda x: "\n\n".join(x)
        }).reset_index()

        # Sort naturally: volume > book_number > hadith_no
        grouped["volume_int"] = grouped["volume"].apply(safe_int)
        grouped["book_int"] = grouped["book_number"].apply(safe_int)
        grouped["hadith_int"] = grouped["hadith_no"].apply(safe_int)
        grouped = grouped.sort_values(by=["volume_int", "book_int", "hadith_int"]).drop(columns=["volume_int", "book_int", "hadith_int"])

        # Chunk each row
        for _, row in grouped.iterrows():
            chunk_set = build_chunks(row, global_chunk_idx)
            all_chunks.extend(chunk_set)
            global_chunk_idx += len(chunk_set)

    # Save
    df_chunks = pd.DataFrame(all_chunks)
    df_chunks.to_csv(OUTPUT_CSV, index=False)
    df_chunks.to_json(OUTPUT_JSONL, orient="records", lines=True)
    print(f"\n✅ Done! {len(df_chunks)} chunks saved to:\n - {OUTPUT_CSV}\n - {OUTPUT_JSONL}")

# Run
if __name__ == "__main__":
    process_alkafi_folder(INPUT_DIR)
