import os
from dotenv import load_dotenv
from pinecone import Pinecone, ServerlessSpec

# Load your .env
load_dotenv()

PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_ENVIRONMENT = os.getenv("PINECONE_ENVIRONMENT")  # Optional with new SDK

# Index settings
INDEX_NAME = "deen-index-v2"
DIMENSION = 768  # from all-mpnet-base-v2
METRIC = "cosine"

# Create Pinecone instance
pc = Pinecone(api_key=PINECONE_API_KEY)

# Check if it exists
if INDEX_NAME not in pc.list_indexes().names():
    pc.create_index(
        name=INDEX_NAME,
        dimension=DIMENSION,
        metric=METRIC,
        spec=ServerlessSpec(
            cloud="aws",  # or "aws" if you're using AWS
            region="us-east-1"
        )
    )
    print(f"✅ Index '{INDEX_NAME}' created.")
else:
    print(f"ℹ️ Index '{INDEX_NAME}' already exists.")
