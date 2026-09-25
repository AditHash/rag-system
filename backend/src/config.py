"""Small settings module; values come from the process environment."""

import os

DATABASE_URL = os.getenv("DATABASE_URL", "")
AWS_REGION = os.getenv("AWS_REGION", "ap-south-1")
EMBEDDING_MODEL_ID = os.getenv(
    "BEDROCK_EMBEDDING_MODEL_ID", "amazon.titan-embed-text-v2:0"
)
COLLECTION_NAME = os.getenv("VECTOR_COLLECTION", "documents")
API_KEY = os.getenv("API_KEY", "")
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "1000"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "150"))
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
