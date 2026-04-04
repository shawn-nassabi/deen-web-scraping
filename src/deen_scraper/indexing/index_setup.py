"""Create the dense and sparse Pinecone indexes.

Run as a module to create both indexes at once, or call
``create_indexes()`` from other scripts.

    python -m deen_scraper.indexing.index_setup
"""

from __future__ import annotations

import os

from dotenv import load_dotenv
from pinecone import Pinecone, ServerlessSpec

from deen_scraper.config import (
    DENSE_INDEX_NAME,
    SPARSE_INDEX_NAME,
    EMBEDDING_MODEL,
)

_DENSE_DIMENSION = 768  # all-mpnet-base-v2


def create_indexes(
    *,
    dense_name: str = DENSE_INDEX_NAME,
    sparse_name: str = SPARSE_INDEX_NAME,
    region: str = "us-east-1",
    cloud: str = "aws",
) -> None:
    """Create dense and/or sparse indexes if they do not already exist."""
    load_dotenv()
    pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
    existing = pc.list_indexes().names()

    if dense_name not in existing:
        print(f"Creating dense index '{dense_name}' …")
        pc.create_index(
            name=dense_name,
            dimension=_DENSE_DIMENSION,
            metric="cosine",
            spec=ServerlessSpec(cloud=cloud, region=region),
        )
        print(f"  ✅ Dense index '{dense_name}' created.")
    else:
        print(f"  ℹ️  Dense index '{dense_name}' already exists.")

    if sparse_name not in existing:
        print(f"Creating sparse index '{sparse_name}' …")
        pc.create_index(
            name=sparse_name,
            metric="dotproduct",
            vector_type="sparse",
            spec=ServerlessSpec(cloud=cloud, region=region),
        )
        print(f"  ✅ Sparse index '{sparse_name}' created.")
    else:
        print(f"  ℹ️  Sparse index '{sparse_name}' already exists.")


if __name__ == "__main__":
    create_indexes()
