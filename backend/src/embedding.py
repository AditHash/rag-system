"""Amazon Bedrock adapter for Titan Text Embeddings V2."""

import json
import math
import time
from typing import Any

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from src.config import AWS_REGION, BEDROCK_EMBEDDING_DIMENSIONS, BEDROCK_EMBEDDING_MODEL_ID

MAX_INPUT_CHARACTERS = 30_000
MAX_ATTEMPTS = 3
RETRYABLE_ERROR_CODES = {
    "InternalServerException",
    "ServiceUnavailableException",
    "ThrottlingException",
    "TooManyRequestsException",
}


class EmbeddingProviderError(RuntimeError):
    """Bedrock failed or returned an invalid embedding response."""


class BedrockEmbeddingProvider:
    """Create Titan V2 embeddings, checking every result against the DB dimension."""

    def __init__(self, client: Any | None = None, model_id: str | None = None) -> None:
        self.client = (
            client
            if client is not None
            else boto3.client(
                "bedrock-runtime",
                region_name=AWS_REGION,
                config=Config(retries={"total_max_attempts": 1}),
            )
        )
        self.model_id = model_id or BEDROCK_EMBEDDING_MODEL_ID

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Embed each nonempty text with one bounded model request."""
        for text in texts:
            if not text.strip():
                raise ValueError("text to embed must not be empty")
            if len(text) > MAX_INPUT_CHARACTERS:
                raise ValueError(f"text to embed exceeds {MAX_INPUT_CHARACTERS} characters")
        return [self._embed_one(text) for text in texts]

    def embed_query(self, question: str) -> list[float]:
        """Embed one query with the same model and dimension used for documents."""
        return self.embed_texts([question])[0]

    def _embed_one(self, text: str) -> list[float]:
        request_body = json.dumps(
            {
                "inputText": text,
                "dimensions": BEDROCK_EMBEDDING_DIMENSIONS,
                "normalize": True,
            }
        )

        for attempt in range(MAX_ATTEMPTS):
            try:
                response = self.client.invoke_model(
                    modelId=self.model_id,
                    body=request_body,
                    contentType="application/json",
                    accept="application/json",
                )
                return self._parse_embedding(response["body"])
            except ClientError as error:
                error_code = error.response.get("Error", {}).get("Code", "")
                if error_code in RETRYABLE_ERROR_CODES and attempt < MAX_ATTEMPTS - 1:
                    time.sleep(0.25 * (2**attempt))
                    continue
                raise EmbeddingProviderError("Bedrock embedding request failed") from None
            except BotoCoreError:
                raise EmbeddingProviderError("Bedrock embedding request failed") from None
            except (KeyError, TypeError, ValueError):
                raise EmbeddingProviderError(
                    "Bedrock returned an invalid embedding response"
                ) from None

        raise EmbeddingProviderError("Bedrock embedding request failed")

    @staticmethod
    def _parse_embedding(body: Any) -> list[float]:
        try:
            payload = json.loads(body.read())
        finally:
            close = getattr(body, "close", None)
            if close is not None:
                close()

        embedding = payload.get("embedding") if isinstance(payload, dict) else None
        if not isinstance(embedding, list) or len(embedding) != BEDROCK_EMBEDDING_DIMENSIONS:
            raise ValueError("embedding dimension does not match the database schema")
        if any(
            not isinstance(value, (int, float)) or isinstance(value, bool) for value in embedding
        ):
            raise ValueError("embedding contains a non-numeric value")

        vector = [float(value) for value in embedding]
        if any(not math.isfinite(value) for value in vector):
            raise ValueError("embedding contains a non-finite value")
        return vector
