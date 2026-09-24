"""Runtime settings; environment values override the defaults below."""

import os

AWS_REGION = os.getenv("AWS_REGION", "ap-south-1")
BEDROCK_EMBEDDING_DIMENSIONS = 1024
BEDROCK_EMBEDDING_MODEL_ID = os.getenv("BEDROCK_EMBEDDING_MODEL_ID", "amazon.titan-embed-text-v2:0")
BEDROCK_CHAT_MODEL_ID = os.getenv("BEDROCK_CHAT_MODEL_ID", "qwen.qwen3-32b-v1:0")
BEDROCK_THINKING_MODEL_ID = os.getenv("BEDROCK_THINKING_MODEL_ID", "openai.gpt-oss-20b-1:0")
BEDROCK_RERANKER_MODEL_ID = os.getenv("BEDROCK_RERANKER_MODEL_ID", "cohere.rerank-v3-5:0")
