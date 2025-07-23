import os
import json
import numpy as np
from tqdm import tqdm
from dotenv import load_dotenv
from pinecone import Pinecone

from chunksets.sunni_book_cleaner import process_sunni_csv
from chunksets.text_prepocesser import compress_text, normalize_text
from sklearn.feature_extraction.text import TfidfVectorizer
import string

# Load environment
load_dotenv()
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
INDEX_NAME = "deen-index-v2-sparse"  # <-- Use a separate sparse index
NAMESPACE = "ns1"

def run_sparse_indexer(records):

    # Normalize text for sparse vectorization
    doc_texts = [normalize_text(r["text_chunk"]) for r in records]

    # Fit TF-IDF vectorizer
    vectorizer = TfidfVectorizer(
        preprocessor=None,  # already preprocessed
        stop_words='english',
        analyzer='word',
        lowercase=False,
        use_idf=True,
        smooth_idf=True,
        sublinear_tf=True,
        norm=None
    )
    tfidf_matrix = vectorizer.fit_transform(doc_texts)

    # Connect to Pinecone
    pc = Pinecone(api_key=PINECONE_API_KEY)
    index = pc.Index(INDEX_NAME)


    # Format for Pinecone sparse upsert
    def tfidf_to_sparse(r, chunk_idx, vec):
        vec_array = vec.toarray().squeeze()
        indices = np.nonzero(vec_array)[0].tolist()
        values = vec_array[indices].tolist()

        if not indices:
            print(f"Skipping empty vector for chunk: {r['chunk_id']} | hadith_id: {r.get('hadith_id', '')}")
            return None

        hadith_id = f"{r['sect']}_{r['collection']}_{r.get('volume', '')}_{r.get('chapter_number', '')}_{r.get('hadith_no', '')}"

        metadata = {
            **{k: v for k, v in r.items() if k != "text_chunk"},
            "text_en": compress_text(r.get("text_en", "")),
            "text_ar": compress_text(r.get("text_ar", "")),
            "hadith_id": hadith_id
        }

        return {
            "id": f"{r['collection']}_{chunk_idx}",
            "sparse_values": {
                "indices": indices,
                "values": values
            },
            "metadata": metadata
        }


    # Create sparse vectors
    vectors = []
    for i, r in enumerate(records):
        sparse_vec = tfidf_to_sparse(r, i, tfidf_matrix[i])
        if sparse_vec:
            vectors.append(sparse_vec)

    # Upload in batches
    BATCH_SIZE = 50
    for i in tqdm(range(0, len(vectors), BATCH_SIZE), desc=" Uploading sparse vectors"):
        batch = vectors[i:i + BATCH_SIZE]
        index.upsert(vectors=batch, namespace=NAMESPACE)

    print(" Sparse vector upsert complete.")

def run_shia_books_indexer():
    # Load chunked hadith records (already chunked)
    with open("../datasets/cleaned_data/nahjal_balagha_cleaned_chunks.jsonl", "r", encoding="utf-8") as f:
        records = [json.loads(line) for line in f]
    print(f" Loaded {len(records)} records from Nahj al-Balagha chunks.")
    run_sparse_indexer(records)
    with open("../datasets/cleaned_data/alkafi_cleaned_chunks.jsonl", "r", encoding="utf-8") as f:
        records = [json.loads(line) for line in f]
    print(f" Loaded {len(records)} records from Al Kafi chunks.")

def run_sunni_books_indexer():
    """ Call this function in the main script to run the dense indexer for Sunni files."""
    sahih_muslim = process_sunni_csv("../datasets/Sahih_Muslim_8b_all_books.csv", "sahih-muslim")
    run_sparse_indexer(sahih_muslim)
    print(f"Processed {len(sahih_muslim)} Sahih Muslim chunks.")
    sahih_bukhari = process_sunni_csv("../datasets/Sahih_al-Bukhari_all_books.csv", "sahih-bukhari")
    run_sparse_indexer(sahih_bukhari)
    print(f"Processed {len(sahih_bukhari)} Sahih Bukhari chunks.")
    tirmidhi = process_sunni_csv("../datasets/Jami`_at-Tirmidhi_all_books.csv", "tirmidhi")
    run_sparse_indexer(tirmidhi)
    print(f"Processed {len(tirmidhi)} Tirmdhi chunks.")
    abi_dawud = process_sunni_csv("../datasets/Sunan_Abi_Dawud_all_books.csv", "abu-dawood")
    run_sparse_indexer(abi_dawud)
    print(f"Processed {len(abi_dawud)} Abi Dawud chunks.")
    an_nasai = process_sunni_csv("../datasets/Sunan_an-Nasa'i_all_books.csv", "an-nasai")
    run_sparse_indexer(an_nasai)
    print(f"Processed {len(an_nasai)} An Nasa' chunks.")

if __name__ == "__main__":
    first_input = input("Do you want to run the sparse indexer for Sunni files? (y/n): ").lower()
    if first_input == 'y':
        run_sunni_books_indexer()
    else:
        print("Skipping Sunni files... ")
    second_input = input("Do you want to run the sparse indexer for Shia files? (y/n): ").lower()
    if second_input == 'y':
        run_shia_books_indexer()
    else:
        print("Exiting without indexing shia files...")


