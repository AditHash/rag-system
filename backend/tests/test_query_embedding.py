"""Query embedding boundary checks use a deterministic fake provider."""

import pytest

from src.config import BEDROCK_EMBEDDING_DIMENSIONS
from src.query_embedding import EmbeddingModelMismatchError, embed_query


class FakeQueryEmbeddingProvider:
    def __init__(self, vector: list[float] | None = None, model_id: str = "embedding-test"):
        self.model_id = model_id
        self.vector = vector or [0.25] * BEDROCK_EMBEDDING_DIMENSIONS
        self.calls: list[str] = []

    def embed_query(self, question: str) -> list[float]:
        self.calls.append(question)
        return self.vector


def test_embed_query_returns_valid_vector_from_matching_model() -> None:
    provider = FakeQueryEmbeddingProvider()

    vector = embed_query("What does the source say?", provider, "embedding-test")

    assert len(vector) == BEDROCK_EMBEDDING_DIMENSIONS
    assert vector == [0.25] * BEDROCK_EMBEDDING_DIMENSIONS
    assert provider.calls == ["What does the source say?"]


def test_embed_query_rejects_empty_question_before_provider_call() -> None:
    provider = FakeQueryEmbeddingProvider()

    with pytest.raises(ValueError, match="question must not be empty"):
        embed_query("  ", provider, "embedding-test")

    assert provider.calls == []


def test_embed_query_rejects_model_mismatch_before_provider_call() -> None:
    provider = FakeQueryEmbeddingProvider()

    with pytest.raises(EmbeddingModelMismatchError, match="does not match"):
        embed_query("question", provider, "different-index-model")

    assert provider.calls == []


def test_embed_query_rejects_invalid_vector_shape() -> None:
    provider = FakeQueryEmbeddingProvider(vector=[0.25])

    with pytest.raises(ValueError, match="dimension"):
        embed_query("question", provider, "embedding-test")
