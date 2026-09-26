"""Small settings module; values come from the process environment."""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

DATABASE_URL = os.getenv("DATABASE_URL", "")
JWT_SECRET = os.getenv("JWT_SECRET", "")
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "720"))
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
EMBEDDING_MODEL_ID = os.getenv(
    "BEDROCK_EMBEDDING_MODEL_ID", "amazon.titan-embed-text-v2:0"
)
CHAT_MODEL_ID = os.getenv("BEDROCK_CHAT_MODEL_ID", "qwen.qwen3-32b-v1:0")
THINKING_MODEL_ID = os.getenv(
    "BEDROCK_THINKING_MODEL_ID", "openai.gpt-oss-20b-1:0"
)
RERANK_MODEL_ID = os.getenv("BEDROCK_RERANK_MODEL_ID", "cohere.rerank-v3-5:0")
COLLECTION_NAME = os.getenv("VECTOR_COLLECTION", "documents")
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "1000"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "150"))
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
