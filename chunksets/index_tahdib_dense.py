"""
Dense index upsert for Tahdib al-Ahkam chunks.
Uploads sentence embeddings of all hadith chunks to the dense Pinecone index.
"""
import os
import json
from tqdm import tqdm
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer
from pinecone import Pinecone

# Load chunksets from same repo
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from chunksets.text_prepocesser import compress_text

# Load environment
load_dotenv()
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")

# Pinecone config
INDEX_NAME = "deen-index-v2"
NAMESPACE = "ns1"
BATCH_SIZE = 50

# Path to cleaned chunks
CHUNKS_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "datasets", "cleaned_data", "tahdib_al_ahkam_cleaned_chunks.jsonl"
)

# Load embedding model
model = SentenceTransformer('sentence-transformers/all-mpnet-base-v2')

# Create Pinecone client
pc = Pinecone(api_key=PINECONE_API_KEY)
index = pc.Index(INDEX_NAME)


def run_dense_indexer(records):
    print(f" Uploading {len(records)} dense vectors...")

    # Batch upload
    for i in tqdm(range(0, len(records), BATCH_SIZE), desc="Uploading to Pinecone"):
        batch = records[i:i + BATCH_SIZE]

        # Prepare embedding input with context
        texts_to_embed = [
            f"""
Collection: {r.get("collection", "")}
Volume: {r.get("volume", "")}
Chapter No: {r.get("chapter_number", "")}
Chapter Title: {r.get("chapter_title", "")}
Reference: {r.get("cross_references", "")}
Source Scholar: {r.get("source_scholar", "")}
Page: {r.get("page_start", "")}-{r.get("page_end", "")}
Topic Tags: {", ".join(r.get("topic_tags", []))}
{r["text_chunk"]}
""".strip()
            for r in batch
        ]

        embeddings = model.encode(texts_to_embed, show_progress_bar=False).tolist()

        vectors = []
        for r, emb in zip(batch, embeddings):
            metadata = {
                **{k: v for k, v in r.items() if k != "text_chunk" and k not in ("text_en", "text_ar", "commentary")},
                "text_en": compress_text(r["text_chunk"]),  # chunk text, not full hadith
                "text_ar": compress_text(r.get("text_ar", "")[:2000]),
                "cross_references": r.get("cross_references", "")[:2000],
            }
            vectors.append((r["chunk_id"], emb, metadata))

        index.upsert(vectors=vectors, namespace=NAMESPACE)

    print(" Upload to Pinecone complete.")


def main():
    if not os.path.exists(CHUNKS_FILE):
        raise FileNotFoundError(f"Input file {CHUNKS_FILE} does not exist.")

    with open(CHUNKS_FILE, 'r', encoding='utf-8') as f:
        records = [json.loads(line.strip()) for line in f if line.strip()]

    print(f"Loaded {len(records)} Tahdib al-Ahkam chunks.")
    run_dense_indexer(records)
    print(f"Processed {len(records)} Tahdib al-Ahkam chunks.")


if __name__ == "__main__":
    main()
