"""Optional Bedrock reranking with an explicit original-order fallback."""

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from src.config import BEDROCK_RERANKER_MODEL_ID, BEDROCK_RERANKER_REGION
from src.retrieval import MAX_RETRIEVAL_TOP_K, RetrievalCandidate

DEFAULT_RERANK_TOP_K = 5
MAX_RERANK_TEXT_CHARACTERS = 32_000


class RerankerError(RuntimeError):
    """Reranking failed or returned an invalid result."""


@dataclass(frozen=True)
class RerankerMatch:
    index: int
    relevance_score: float


@dataclass(frozen=True)
class RerankedCandidate:
    candidate: RetrievalCandidate
    relevance_score: float | None


@dataclass(frozen=True)
class RerankOutcome:
    candidates: list[RerankedCandidate]
    reranked: bool
    model_id: str
    fallback_reason: str | None


class Reranker(Protocol):
    model_id: str

    def rerank(
        self, query: str, candidates: Sequence[RetrievalCandidate], number_of_results: int
    ) -> list[RerankerMatch]: ...


class BedrockReranker:
    """Call Bedrock's Rerank operation and map result indexes to input candidates."""

    def __init__(
        self,
        client: Any | None = None,
        model_id: str | None = None,
        region_name: str | None = None,
    ) -> None:
        self.model_id = model_id or BEDROCK_RERANKER_MODEL_ID
        self.region_name = region_name or BEDROCK_RERANKER_REGION
        if not self.model_id or not self.region_name:
            raise ValueError("reranker model ID and region are required")
        self.client = (
            client
            if client is not None
            else boto3.client(
                "bedrock-agent-runtime",
                region_name=self.region_name,
                config=Config(
                    connect_timeout=3,
                    read_timeout=15,
                    retries={"total_max_attempts": 1},
                ),
            )
        )

    def rerank(
        self, query: str, candidates: Sequence[RetrievalCandidate], number_of_results: int
    ) -> list[RerankerMatch]:
        _validate_request(query, candidates, number_of_results)
        sources = [
            {
                "type": "INLINE",
                "inlineDocumentSource": {
                    "type": "TEXT",
                    "textDocument": {"text": candidate.content},
                },
            }
            for candidate in candidates
        ]
        try:
            response = self.client.rerank(
                queries=[{"type": "TEXT", "textQuery": {"text": query}}],
                sources=sources,
                rerankingConfiguration={
                    "type": "BEDROCK_RERANKING_MODEL",
                    "bedrockRerankingConfiguration": {
                        "modelConfiguration": {"modelArn": self._model_arn()},
                        "numberOfResults": number_of_results,
                    },
                },
            )
        except (BotoCoreError, ClientError):
            raise RerankerError("Bedrock reranking request failed") from None
        return _parse_matches(response, len(candidates), number_of_results)

    def _model_arn(self) -> str:
        if self.model_id.startswith("arn:"):
            return self.model_id
        return f"arn:aws:bedrock:{self.region_name}::foundation-model/{self.model_id}"


def rerank_candidates(
    query: str,
    candidates: Sequence[RetrievalCandidate],
    reranker: Reranker,
    top_k: int = DEFAULT_RERANK_TOP_K,
) -> RerankOutcome:
    """Rerank candidates, or return the original order without made-up scores."""
    if not candidates:
        return RerankOutcome([], False, reranker.model_id, None)
    if not query.strip():
        raise ValueError("query must not be empty")

    result_count = min(clamp_rerank_top_k(top_k), len(candidates))
    try:
        matches = reranker.rerank(query, candidates, result_count)
        _validate_matches(matches, len(candidates), result_count)
    except RerankerError:
        passthrough = [
            RerankedCandidate(candidate, None) for candidate in candidates[:result_count]
        ]
        return RerankOutcome(passthrough, False, reranker.model_id, "provider_error")

    ordered = [
        RerankedCandidate(candidates[match.index], match.relevance_score) for match in matches
    ]
    return RerankOutcome(ordered, True, reranker.model_id, None)


def clamp_rerank_top_k(top_k: int) -> int:
    """Bound reranker output and its associated model request size."""
    return min(max(top_k, 1), MAX_RETRIEVAL_TOP_K)


def _validate_request(
    query: str, candidates: Sequence[RetrievalCandidate], number_of_results: int
) -> None:
    if not query.strip() or len(query) > MAX_RERANK_TEXT_CHARACTERS:
        raise ValueError("reranker query is empty or too long")
    if not candidates:
        raise ValueError("at least one candidate is required")
    if len(candidates) > MAX_RETRIEVAL_TOP_K:
        raise ValueError("candidate count exceeds the reranker limit")
    if not 1 <= number_of_results <= len(candidates):
        raise ValueError("number_of_results must fit the candidate count")
    if any(
        not candidate.content or len(candidate.content) > MAX_RERANK_TEXT_CHARACTERS
        for candidate in candidates
    ):
        raise ValueError("candidate text is empty or too long")


def _parse_matches(
    response: object, candidate_count: int, expected_count: int
) -> list[RerankerMatch]:
    try:
        raw_results = response["results"]  # type: ignore[index]
        if not isinstance(raw_results, list) or len(raw_results) != expected_count:
            raise ValueError("unexpected result count")
        matches = []
        for result in raw_results:
            raw_score = result["relevanceScore"]
            if not isinstance(raw_score, (int, float)) or isinstance(raw_score, bool):
                raise ValueError("score is not numeric")
            matches.append(
                RerankerMatch(
                    index=result["index"],
                    relevance_score=float(raw_score),
                )
            )
        _validate_matches(matches, candidate_count, expected_count)
        return matches
    except (KeyError, TypeError, ValueError, OverflowError):
        raise RerankerError("Bedrock returned an invalid reranking response") from None


def _validate_matches(
    matches: Sequence[RerankerMatch], candidate_count: int, expected_count: int
) -> None:
    if len(matches) != expected_count:
        raise RerankerError("Bedrock returned an invalid reranking response")
    seen_indexes: set[int] = set()
    for match in matches:
        if (
            not isinstance(match.index, int)
            or isinstance(match.index, bool)
            or not 0 <= match.index < candidate_count
            or match.index in seen_indexes
            or not isinstance(match.relevance_score, (int, float))
            or isinstance(match.relevance_score, bool)
            or not math.isfinite(match.relevance_score)
        ):
            raise RerankerError("Bedrock returned an invalid reranking response")
        seen_indexes.add(match.index)
