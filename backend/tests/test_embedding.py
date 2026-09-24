"""Bedrock embedding tests use fake responses and make no inference calls."""

import json
from io import BytesIO

import pytest
from botocore.exceptions import ClientError

from src.config import BEDROCK_EMBEDDING_DIMENSIONS
from src.embedding import BedrockEmbeddingProvider, EmbeddingProviderError


class FakeBedrockClient:
    def __init__(self, vectors: list[list[float]] | None = None) -> None:
        self.vectors = vectors or [[0.25] * BEDROCK_EMBEDDING_DIMENSIONS]
        self.calls: list[dict[str, object]] = []
        self.errors: list[Exception] = []

    def invoke_model(self, **kwargs: object) -> dict[str, BytesIO]:
        self.calls.append(kwargs)
        if self.errors:
            raise self.errors.pop(0)
        vector = self.vectors[min(len(self.calls) - 1, len(self.vectors) - 1)]
        return {"body": BytesIO(json.dumps({"embedding": vector}).encode())}


def _throttle_error() -> ClientError:
    return ClientError(
        {"Error": {"Code": "ThrottlingException", "Message": "service busy"}},
        "InvokeModel",
    )


def test_embedding_request_uses_selected_model_and_schema_dimension() -> None:
    client = FakeBedrockClient()
    provider = BedrockEmbeddingProvider(client=client, model_id="model-test")

    vectors = provider.embed_texts(["document text"])
    request = client.calls[0]

    assert len(vectors) == 1
    assert len(vectors[0]) == BEDROCK_EMBEDDING_DIMENSIONS
    assert request["modelId"] == "model-test"
    assert request["contentType"] == "application/json"
    assert request["accept"] == "application/json"
    assert json.loads(request["body"]) == {
        "inputText": "document text",
        "dimensions": BEDROCK_EMBEDDING_DIMENSIONS,
        "normalize": True,
    }


def test_query_and_documents_use_same_embedding_path() -> None:
    client = FakeBedrockClient()
    provider = BedrockEmbeddingProvider(client=client)

    query_vector = provider.embed_query("question")
    document_vectors = provider.embed_texts(["document"])

    assert len(query_vector) == len(document_vectors[0]) == BEDROCK_EMBEDDING_DIMENSIONS
    assert client.calls[0]["modelId"] == client.calls[1]["modelId"]


def test_empty_list_makes_no_calls_and_invalid_text_is_rejected() -> None:
    client = FakeBedrockClient()
    provider = BedrockEmbeddingProvider(client=client)

    assert provider.embed_texts([]) == []
    assert client.calls == []
    with pytest.raises(ValueError, match="must not be empty"):
        provider.embed_texts(["  "])
    with pytest.raises(ValueError, match="exceeds"):
        provider.embed_texts(["x" * 30_001])
    assert client.calls == []


@pytest.mark.parametrize(
    "vector",
    [
        [0.1],
        ["bad"] * BEDROCK_EMBEDDING_DIMENSIONS,
        [float("nan")] * BEDROCK_EMBEDDING_DIMENSIONS,
    ],
)
def test_bad_dimension_or_values_fail_closed(vector: list[float]) -> None:
    provider = BedrockEmbeddingProvider(client=FakeBedrockClient([vector]))

    with pytest.raises(EmbeddingProviderError, match="invalid embedding response"):
        provider.embed_texts(["text"])


def test_throttling_is_retried_with_bounded_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeBedrockClient()
    client.errors = [_throttle_error(), _throttle_error()]
    provider = BedrockEmbeddingProvider(client=client)
    delays: list[float] = []
    monkeypatch.setattr("src.embedding.time.sleep", delays.append)

    result = provider.embed_texts(["text"])

    assert len(result[0]) == BEDROCK_EMBEDDING_DIMENSIONS
    assert len(client.calls) == 3
    assert delays == [0.25, 0.5]


def test_retry_exhaustion_does_not_expose_provider_details() -> None:
    client = FakeBedrockClient()
    client.errors = [_throttle_error(), _throttle_error(), _throttle_error()]
    provider = BedrockEmbeddingProvider(client=client)

    with pytest.raises(EmbeddingProviderError) as error:
        provider.embed_texts(["text"])

    assert len(client.calls) == 3
    assert "service busy" not in str(error.value)


def test_nonretryable_aws_error_fails_without_extra_attempts() -> None:
    client = FakeBedrockClient()
    client.errors = [
        ClientError(
            {"Error": {"Code": "AccessDeniedException", "Message": "private detail"}},
            "InvokeModel",
        )
    ]
    provider = BedrockEmbeddingProvider(client=client)

    with pytest.raises(EmbeddingProviderError) as error:
        provider.embed_texts(["text"])

    assert len(client.calls) == 1
    assert "private detail" not in str(error.value)
