import os
import json
import numpy as np
from tqdm import tqdm
from dotenv import load_dotenv
from pinecone import Pinecone
from chunksets.text_prepocesser import compress_text, normalize_text
from sklearn.feature_extraction.text import TfidfVectorizer
import string

# Load environment
load_dotenv()
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
INDEX_NAME = "deen-index-v2-sparse"  # <-- Use a separate sparse index
NAMESPACE = "ns1"

# Load chunked hadith records (already chunked)
with open("../datasets/cleaned_data/nahjal_balagha_cleaned_chunks.jsonl", "r", encoding="utf-8") as f:
    records = [json.loads(line) for line in f]

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
vectors = [tfidf_to_sparse(r, i, tfidf_matrix[i]) for i, r in enumerate(records)]

# Upload in batches
BATCH_SIZE = 50
for i in tqdm(range(0, len(vectors), BATCH_SIZE), desc=" Uploading sparse vectors"):
    batch = vectors[i:i + BATCH_SIZE]
    index.upsert(vectors=batch, namespace=NAMESPACE)

print(" Sparse vector upsert complete.")
