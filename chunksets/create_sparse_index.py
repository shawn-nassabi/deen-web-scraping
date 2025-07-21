import os
from dotenv import load_dotenv
from pinecone import Pinecone, ServerlessSpec

# Load API key and region
load_dotenv()
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_ENVIRONMENT = os.getenv("PINECONE_ENVIRONMENT")  # ex: "us-east-1-aws"

# Init Pinecone client
pc = Pinecone(api_key=PINECONE_API_KEY)

# Index name and config
INDEX_NAME = "deen-index-v2-sparse"
METRIC = "dotproduct"

# Check if already exists
if INDEX_NAME in pc.list_indexes().names():
    print(f" Index '{INDEX_NAME}' already exists.")
else:
    print(f" Creating sparse index '{INDEX_NAME}'...")
    pc.create_index(
        name=INDEX_NAME,
        metric=METRIC,
        vector_type="sparse",
        spec=ServerlessSpec(
            cloud="aws",
            region=PINECONE_ENVIRONMENT
        )
    )
    print(f" Index '{INDEX_NAME}' created.")

