import os
import re
import pandas as pd
from langchain.text_splitter import RecursiveCharacterTextSplitter
from text_prepocesser import compress_text



text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=350,
    chunk_overlap=50,
    separators=["\n\n", "\n", ".", " "]
)


def process_sunni_csv(csv_path, collection_name, sect="sunni"):
    df = pd.read_csv(csv_path)

    # Drop rows with missing data
    df.dropna(subset=["english", "arabic"], inplace=True)

    entries = []
    chunk_counter = 0

    for _, row in df.iterrows():
        # Parse fields
        book_raw = row.get("book", "")
        chapter_raw = row.get("in_book_reference", "")
        grade_en = str(row.get("english_grade", "")).strip() or ""
        grade_ar = str(row.get("arabic_grade", "")).strip() or ""

        # Parse book number and title
        match = re.match(r"\s*(\d+)[\.:\-\)]?\s*(.+)?", book_raw)
        book_number, book_title = "", ""
        if match:
            book_number = match.group(1)
            book_title = match.group(2) or ""

        # Parse Chapter/Hadith Number
        hadith_no = ""
        match = re.match(r"Book\s*(\d+)\s*,\s*Hadith\s*(\d+)", chapter_raw)
        if match:
            book_number = match.group(1)
            hadith_no = match.group(2)

            # Clean texts
        text_en_full = row["english"]
        text_ar_full = row["arabic"]

        # Compress full text
        compressed_en = compress_text(text_en_full)
        compressed_ar = compress_text(text_ar_full)

        # Determine hadith ID
        hadith_id = f"{sect}_{collection_name}_{book_number}_{hadith_no}"

        # Apply chunking
        chunks = (
            text_splitter.split_text(text_en_full)
            if len(text_en_full.split()) > 400 else [text_en_full]
        )

        for i, chunk in enumerate(chunks):
            metadata = {
                "sect": sect,
                "collection": collection_name,
                "author": "",
                "volume": "",
                "book_number": book_number,
                "book_title": book_title,
                "chapter_title": "",
                "hadith_no": hadith_no,
                "lang": "en",
                "chunk_id": f"{collection_name}_{chunk_counter}",
                "grade_en": grade_en,
                "grade_ar": grade_ar,
                "text_en": compressed_en,
                "text_ar": compressed_ar,
                "hadith_id": hadith_id
            }

            entries.append({
                "text_chunk": chunk,
                **metadata
            })
            chunk_counter += 1

    return entries


if __name__ == "__main__":
    sahih_muslim = process_sunni_csv("../datasets/Sahih_Muslim_8b_all_books.csv", "sahih-muslim")
    print(f"Processed {len(sahih_muslim)} Sahih Muslim chunks.")
    sahih_bukhari = process_sunni_csv("../datasets/Sahih_al-Bukhari_all_books.csv", "sahih-bukhari")
    print(f"Processed {len(sahih_bukhari)} Sahih Bukhari chunks.")
    tirmidhi = process_sunni_csv("../datasets/Jami`_at-Tirmidhi_all_books.csv", "tirmidhi")
    print(f"Processed {len(sahih_muslim)} Tirmdhi chunks.")
    abi_dawud = process_sunni_csv("../datasets/Sunan_Abi_Dawud_all_books.csv", "abu-dawood")
    print(f"Processed {len(abi_dawud)} Abi Dawud chunks.")
    an_nasai = process_sunni_csv("../datasets/Sunan_an-Nasa'i_all_books.csv", "an-nasai")
    print(f"Processed {len(an_nasai)} An Nasa' chunks.")
