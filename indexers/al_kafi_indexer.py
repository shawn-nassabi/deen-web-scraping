import os
import pandas as pd
import re
from langchain.text_splitter import RecursiveCharacterTextSplitter

CSV_DIR = "../datasets/Alkafi"
OUTPUT_CSV = "../chunksets/alkafi_cleaned_chunks.csv"
OUTPUT_JSONL = "../chunksets/alkafi_cleaned_chunks.jsonl"

# Chunking config
CHUNK_SIZE = 350
CHUNK_OVERLAP = 50

splitter = RecursiveCharacterTextSplitter(
    chunk_size=CHUNK_SIZE,
    chunk_overlap=CHUNK_OVERLAP,
    separators=["\n\n", "\n", ".", "!", "?", " "]
)


def clean_text(text):
    """Remove leading numbers and strip whitespace."""
    text = str(text).strip()
    return re.sub(r'^\s*\d+\s*[\.\-–]*\s*', '', text)


def split_book_field(book):
    parts = book.split("|")
    if len(parts) == 2:
        return parts[0].strip(), parts[1].strip()
    return "", book.strip()


def extract_hadith_number(hadith_str):
    match = re.search(r'\d+', str(hadith_str))
    return match.group(0) if match else ""


def preprocess_row(row, volume):
    book_number, book_title = split_book_field(row["book"])
    chapter_title = row["chapter"].split("|")[-1].strip()

    metadata_base = {
        "sect": "shia",
        "collection": "al-kafi",
        "author": row["author"].strip(),
        "volume": volume,
        "book_number": book_number,
        "book_title": book_title,
        "chapter_title": chapter_title,
        "hadith_no": extract_hadith_number(row["hadees_number"]),
        "lang": "en",
        "grade_en": "",
        "grade_ar": "",
        "text_ar": row["hadees_arabic"]
    }

    english_text = row["hadees_english"]
    word_count = len(english_text.split())

    if word_count < 400:
        return [{
            **metadata_base,
            "chunk_id": "0",
            "text_en": english_text
        }]

    chunks = splitter.split_text(english_text)
    return [{
        **metadata_base,
        "chunk_id": str(i),
        "text_en": chunk
    } for i, chunk in enumerate(chunks)]


def process_all_csvs():
    all_chunks = []

    for filename in sorted(os.listdir(CSV_DIR)):
        if not filename.endswith(".csv"):
            continue

        volume = filename.split("_Volume")[1].split("_")[0].strip()
        filepath = os.path.join(CSV_DIR, filename)
        df = pd.read_csv(filepath)

        # Drop rows with missing values
        df = df.dropna(subset=["hadees_arabic", "hadees_english"])

        # Clean text columns
        df["hadees_arabic"] = df["hadees_arabic"].apply(clean_text)
        df["hadees_english"] = df["hadees_english"].apply(clean_text)

        print(f"Processing Volume {volume}: {len(df)} rows")

        for _, row in df.iterrows():
            all_chunks.extend(preprocess_row(row, volume))

    # Save to CSV and JSONL
    final_df = pd.DataFrame(all_chunks)
    final_df.to_csv(OUTPUT_CSV, index=False)
    final_df.to_json(OUTPUT_JSONL, orient="records", lines=True)
    print(f"\n✅ Saved {len(final_df)} entries to:")
    print(f" - {OUTPUT_CSV}")
    print(f" - {OUTPUT_JSONL}")


if __name__ == "__main__":
    process_all_csvs()
