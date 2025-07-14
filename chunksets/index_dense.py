import os
import json
import gzip
import base64
from tqdm import tqdm
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer
from pinecone import Pinecone



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

# Path to pre-chunked data
INPUT_JSONL = "../datasets/cleaned_data/nahjal_balagha_cleaned_chunks.jsonl"  # or alkafi_cleaned_chunks.jsonl

# Compression helper
def compress_text(text: str) -> str:
    if not text:
        return ""
    compressed = gzip.compress(text.encode("utf-8"))
    return base64.b64encode(compressed).decode("utf-8")

# Load records
with open(INPUT_JSONL, 'r', encoding='utf-8') as f:
    records = [json.loads(line.strip()) for line in f]

print(f" Loaded {len(records)} records from {INPUT_JSONL}")

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
