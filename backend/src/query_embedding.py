"""Validate query vectors before they are passed to pgvector retrieval."""

import math
from typing import Protocol

from src.config import BEDROCK_EMBEDDING_DIMENSIONS


class QueryEmbeddingProvider(Protocol):
    model_id: str

    def embed_query(self, question: str) -> list[float]: ...


class EmbeddingModelMismatchError(ValueError):
    """The query model differs from the one used to embed indexed chunks."""


def embed_query(
    question: str,
    provider: QueryEmbeddingProvider,
    expected_model_id: str,
) -> list[float]:
    """Embed one nonempty query and verify it matches the document vector space."""
    if not question.strip():
        raise ValueError("question must not be empty")
    if provider.model_id != expected_model_id:
        raise EmbeddingModelMismatchError(
            "query embedding model does not match the indexed document model"
        )

    vector = provider.embed_query(question)
    if len(vector) != BEDROCK_EMBEDDING_DIMENSIONS:
        raise ValueError("query embedding dimension does not match the database schema")
    if any(not isinstance(value, (int, float)) or isinstance(value, bool) for value in vector):
        raise ValueError("query embedding contains a non-numeric value")

    result = [float(value) for value in vector]
    if any(not math.isfinite(value) for value in result):
        raise ValueError("query embedding contains a non-finite value")
    return result
