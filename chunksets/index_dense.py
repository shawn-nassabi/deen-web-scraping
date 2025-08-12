import os
import json
from tqdm import tqdm
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer
from pinecone import Pinecone

from chunksets.sunni_book_cleaner import process_sunni_csv
from chunksets.text_prepocesser import compress_text

load_dotenv()
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_ENVIRONMENT = os.getenv("PINECONE_ENVIRONMENT")

# Pinecone config
INDEX_NAME = "deen-index-v2"
NAMESPACE = "ns1"
BATCH_SIZE = 50

# Load embedding model
model = SentenceTransformer('sentence-transformers/all-mpnet-base-v2')


# Create Pinecone client instance
pc = Pinecone(api_key=PINECONE_API_KEY)
index = pc.Index(INDEX_NAME)

def run_dense_indexer(records):
    # Batch upload
    for i in tqdm(range(0, len(records), BATCH_SIZE), desc="🔄 Uploading to Pinecone"):
        batch = records[i:i + BATCH_SIZE]

        # Prepare embedding input with context
        texts_to_embed = [
            f"""
    Collection: {r.get("collection", "")}
    Volume: {r.get("volume", "")}
    Book: {r.get("book_title", "")}
    Chapter No: {r.get("chapter_number", "")}
    Chapter Title: {r.get("chapter_title", "")}
    Reference: {r.get("reference", "")}
    Hadith URL: {r.get("hadith_url", "")}
    Hadith No: {r.get("hadith_no", "")}
    {r['text_chunk']}
    """.strip()
            for r in batch
        ]

        embeddings = model.encode(texts_to_embed, show_progress_bar=False).tolist()

        vectors = []
        for r, emb in zip(batch, embeddings):
            # Build hadith_id
            hadith_id = f"{r['sect']}_{r['collection']}_{r.get('volume', '')}_{r.get('chapter_number', '')}_{r.get('hadith_no', '')}"

            metadata = {
                **{k: v for k, v in r.items() if k != "text_chunk"},
                "text_en": compress_text(r.get("text_en", "")),
                "text_ar": compress_text(r.get("text_ar", "")),
                "hadith_id": hadith_id
            }

            vectors.append((r["chunk_id"], emb, metadata))

        index.upsert(vectors=vectors, namespace=NAMESPACE)

    print(" Upload to Pinecone complete.")

def shia_file_dense_index_runner(filepath):
    # Load records
    with open(filepath, 'r', encoding='utf-8') as f:
        records = [json.loads(line.strip()) for line in f]

    print(f" Loaded {len(records)} records from {filepath}")
    run_dense_indexer(records)

def read_shia_file():
    """Call this function in the main script to run the dense indexer for selected Shia file."""
    # Path to pre-chunked data
    INPUT_JSONL = "../datasets/cleaned_data/nahjal_balagha_cleaned_chunks.jsonl"  # or alkafi_cleaned_chunks.jsonl
    if not os.path.exists(INPUT_JSONL):
        raise FileNotFoundError(f"Input file {INPUT_JSONL} does not exist.")
    shia_file_dense_index_runner(INPUT_JSONL)

def sunni_file_dense_index_runner():
    """ Call this function in the main script to run the dense indexer for Sunni files."""
    sahih_muslim = process_sunni_csv("../datasets/Sahih_Muslim_8b_all_books.csv", "sahih-muslim")
    run_dense_indexer(sahih_muslim)
    print(f"Processed {len(sahih_muslim)} Sahih Muslim chunks.")
    sahih_bukhari = process_sunni_csv("../datasets/Sahih_al-Bukhari_all_books.csv", "sahih-bukhari")
    run_dense_indexer(sahih_bukhari)
    print(f"Processed {len(sahih_bukhari)} Sahih Bukhari chunks.")
    tirmidhi = process_sunni_csv("../datasets/Jami`_at-Tirmidhi_all_books.csv", "tirmidhi")
    run_dense_indexer(tirmidhi)
    print(f"Processed {len(tirmidhi)} Tirmdhi chunks.")
    abi_dawud = process_sunni_csv("../datasets/Sunan_Abi_Dawud_all_books.csv", "abu-dawood")
    run_dense_indexer(abi_dawud)
    print(f"Processed {len(abi_dawud)} Abi Dawud chunks.")
    an_nasai = process_sunni_csv("../datasets/Sunan_an-Nasa'i_all_books.csv", "an-nasai")
    run_dense_indexer(an_nasai)
    print(f"Processed {len(an_nasai)} An Nasa' chunks.")

if __name__ == "__main__":
    first_input = input("Do you want to run the dense indexer for Sunni files? (y/n): ").lower()
    if first_input == 'y':
        sunni_file_dense_index_runner()
    else:
        print("Skipping Sunni files... ")
    second_input = input("Do you want to run the dense indexer for Shia files? (y/n): ").lower()
    if second_input == 'y':
        read_shia_file()
    else:
        print("Exiting without indexing shia files...")
