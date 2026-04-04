"""Unified sparse indexer -- TF-IDF encode chunks and upsert to Pinecone.

Replaces ``index_sparse.py``, ``index_faqih_sparse.py``,
and ``index_tahdib_sparse.py`` with one parameterised function.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np
from dotenv import load_dotenv
from pinecone import Pinecone
from sklearn.feature_extraction.text import TfidfVectorizer
from tqdm import tqdm

from deen_scraper.config import (
    SPARSE_INDEX_NAME,
    INDEX_BATCH_SIZE,
    PINECONE_NAMESPACE,
    COLLECTIONS,
    CHUNK_FILES,
)
from deen_scraper.utils.text import compress_text, normalize_text


def upload_sparse(
    records,
    index_name=SPARSE_INDEX_NAME,
    batch_size=INDEX_BATCH_SIZE,
    namespace=PINECONE_NAMESPACE,
):
    """TF-IDF encode *records* and upsert sparse vectors to Pinecone."""
    load_dotenv()

    doc_texts = [normalize_text(r["text_chunk"]) for r in records]
    vectorizer = TfidfVectorizer(
        preprocessor=None,
        stop_words="english",
        analyzer="word",
        lowercase=False,
        use_idf=True,
        smooth_idf=True,
        sublinear_tf=True,
        norm=None,
    )
    tfidf_matrix = vectorizer.fit_transform(doc_texts)

    pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
    index = pc.Index(index_name)

    def to_sparse(r, idx, vec):
        arr = vec.toarray().squeeze()
        indices = np.nonzero(arr)[0].tolist()
        values = arr[indices].tolist()
        if not indices:
            print(f"Skipping empty vector for chunk: {r['chunk_id']}")
            return None
        metadata = {
            k: v for k, v in r.items()
            if k not in ("text_chunk", "text_en", "text_ar", "commentary")
        }
        metadata["text_en"] = compress_text(r.get("text_en", "") or r.get("text_chunk", ""))
        metadata["text_ar"] = compress_text(r.get("text_ar", "")[:2000])
        metadata["cross_references"] = r.get("cross_references", "")[:2000]
        return {
            "id": r["chunk_id"],
            "sparse_values": {"indices": indices, "values": values},
            "metadata": metadata,
        }

    vectors = []
    for i, r in enumerate(records):
        sv = to_sparse(r, i, tfidf_matrix[i])
        if sv:
            vectors.append(sv)

    total = len(vectors)
    print(f"Uploading {total} sparse vectors to \'{index_name}\'...")
    for i in tqdm(range(0, total, batch_size), desc="  Upserting sparse"):
        batch = vectors[i : i + batch_size]
        index.upsert(vectors=batch, namespace=namespace)

    print("  Done. Sparse upsert complete.")
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
    """Load chunks for *collection_name* and upload sparse vectors."""
    if chunks_path is None:
        p = CHUNK_FILES.get(collection_name)
        if p is None:
            raise ValueError(f"No chunks path known for collection \'{collection_name}\'")
        chunks_path = str(p)
    records = load_chunks(chunks_path)
    print(f"  Loaded {len(records)} chunks from {chunks_path}")
    return upload_sparse(records)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Sparse indexer (unified)")
    parser.add_argument("--collection", choices=list(CHUNK_FILES.keys()), required=True)
    parser.add_argument("--chunks-path", type=str, default=None)
    args = parser.parse_args()
    index_collection(args.collection, chunks_path=args.chunks_path)


if __name__ == "__main__":
    main()
