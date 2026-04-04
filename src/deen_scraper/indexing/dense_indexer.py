"""Unified dense indexer -- embeds chunk records and upserts to Pinecone.

Replaces the previous three separate dense indexers
(index_dense.py, index_faqih_dense.py, index_tahdib_dense.py)
with a single parameterised function.
"""

from __future__ import annotations

import json
import os
import argparse
from pathlib import Path

from dotenv import load_dotenv
from pinecone import Pinecone
from sentence_transformers import SentenceTransformer
from tqdm import tqdm

from deen_scraper.config import (
    DENSE_INDEX_NAME,
    EMBEDDING_MODEL,
    INDEX_BATCH_SIZE,
    PINECONE_NAMESPACE,
    COLLECTIONS,
    CHUNK_FILES,
)
from deen_scraper.utils.text import compress_text


def build_embedding_context(record: dict, collection_name: str) -> str:
    """Build the text prefix for embedding, using the collection prompt template."""
    meta = COLLECTIONS.get(collection_name, {})
    prompt = meta.get("indexer_prompt", "{text_chunk}")
    return prompt.format(
        author=record.get("author", ""),
        volume=record.get("volume", ""),
        book_title=record.get("book_title", ""),
        chapter_number=record.get("chapter_number", ""),
        chapter_title=record.get("chapter_title", ""),
        hadith_no=record.get("hadith_no", ""),
        grade_en=record.get("grade_en", ""),
        source_scholar=record.get("source_scholar", ""),
        page_start=record.get("page_start", ""),
        page_end=record.get("page_end", ""),
        topic_tags=", ".join(record.get("topic_tags", [])),
        reference=record.get("cross_references", ""),
        title=record.get("title", ""),
        chapters=record.get("chapters", ""),
        verses=record.get("verses", ""),
        verse_reference=record.get("verse_reference", ""),
        translator=record.get("translator", ""),
        text_chunk=record["text_chunk"],
    )


def upload_dense(
    records,
    collection_name="",
    index_name=DENSE_INDEX_NAME,
    model_name=EMBEDDING_MODEL,
    batch_size=INDEX_BATCH_SIZE,
    namespace=PINECONE_NAMESPACE,
):
    """Embed records and upsert dense vectors to Pinecone."""
    load_dotenv()
    pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
    index = pc.Index(index_name)
    model = SentenceTransformer(model_name)

    total = len(records)
    if total == 0:
        print("No records to upload.")
        return 0

    print("Uploading %d dense vectors to %s..." % (total, index_name))

    for i in tqdm(range(0, total, batch_size), desc="  Embedding and upserting"):
        batch = records[i : i + batch_size]
        texts = [build_embedding_context(r, collection_name) for r in batch]
        embeddings = model.encode(texts, show_progress_bar=False).tolist()

        vectors = []
        for r, emb in zip(batch, embeddings):
            metadata = dict(
                (k, v) for k, v in r.items()
                if k not in ("text_chunk", "text_en", "text_ar", "commentary")
            )
            metadata["text_en"] = compress_text(r.get("text_en", "") or r.get("text_chunk", ""))
            metadata["text_ar"] = compress_text(r.get("text_ar", "")[:2000])
            metadata["cross_references"] = r.get("cross_references", "")[:2000]
            vectors.append((r["chunk_id"], emb, metadata))

        index.upsert(vectors=vectors, namespace=namespace)

    print("  Done. Dense upsert complete.")
    return total


def load_chunks(chunks_path):
    """Load chunk records from a JSONL file."""
    records = []
    with open(chunks_path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def index_collection(collection_name, chunks_path=None):
    """Load chunks for collection and upload."""
    if chunks_path is None:
        p = CHUNK_FILES.get(collection_name)
        if p is None:
            raise ValueError("No chunks path known for collection: %s" % collection_name)
        chunks_path = str(p)
    records = load_chunks(chunks_path)
    print("  Loaded %d chunks from %s" % (len(records), chunks_path))
    return upload_dense(records, collection_name=collection_name)


def main():
    parser = argparse.ArgumentParser(description="Dense indexer (unified)")
    parser.add_argument("--collection", choices=list(CHUNK_FILES.keys()), required=True)
    parser.add_argument("--chunks-path", type=str, default=None)
    args = parser.parse_args()
    index_collection(args.collection, chunks_path=args.chunks_path)


if __name__ == "__main__":
    main()
