"""
Sparse index upsert for Tahdib al-Ahkam chunks.
Uploads TF-IDF sparse vectors to the sparse Pinecone index.
"""
import os
import json
import numpy as np
from tqdm import tqdm
from dotenv import load_dotenv
from pinecone import Pinecone
from sklearn.feature_extraction.text import TfidfVectorizer

# Load chunksets from same repo
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from chunksets.text_prepocesser import compress_text, normalize_text

# Load environment
load_dotenv()
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")

# Pinecone config
INDEX_NAME = "deen-index-v2-sparse"
NAMESPACE = "ns1"
BATCH_SIZE = 50

# Path to cleaned chunks
CHUNKS_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "datasets", "cleaned_data", "tahdib_al_ahkam_cleaned_chunks.jsonl"
)


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

        metadata = {
            **{k: v for k, v in r.items() if k != "text_chunk" and k not in ("text_en", "text_ar", "commentary")},
            "text_en": compress_text(r["text_chunk"]),  # chunk text, not full hadith
            "text_ar": compress_text(r.get("text_ar", "")[:2000]),
            "cross_references": r.get("cross_references", "")[:2000],
        }

        return {
            "id": r["chunk_id"],
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
    print(f" Uploading {len(vectors)} sparse vectors...")
    for i in tqdm(range(0, len(vectors), BATCH_SIZE), desc="Uploading sparse vectors"):
        batch = vectors[i:i + BATCH_SIZE]
        index.upsert(vectors=batch, namespace=NAMESPACE)

    print(" Sparse vector upsert complete.")


def main():
    if not os.path.exists(CHUNKS_FILE):
        raise FileNotFoundError(f"Input file {CHUNKS_FILE} does not exist.")

    with open(CHUNKS_FILE, 'r', encoding='utf-8') as f:
        records = [json.loads(line.strip()) for line in f if line.strip()]

    print(f"Loaded {len(records)} Tahdib al-Ahkam chunks.")
    run_sparse_indexer(records)
    print(f"Processed {len(records)} Tahdib al-Ahkam chunks.")


if __name__ == "__main__":
    main()
