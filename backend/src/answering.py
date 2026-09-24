"""Coordinate embedding, scoped retrieval, evidence gating, and generation."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Literal, Protocol
from uuid import UUID

import psycopg

from src.citations import VerifiedSource, source_map, validate_citations
from src.config import (
    BEDROCK_CHAT_MODEL_ID,
    BEDROCK_EMBEDDING_MODEL_ID,
    BEDROCK_THINKING_MODEL_ID,
    EVIDENCE_MIN_COSINE_SIMILARITY,
)
from src.evidence import assess_evidence
from src.generation import GenerationResult
from src.query_embedding import QueryEmbeddingProvider, embed_query
from src.reranking import DEFAULT_RERANK_TOP_K, Reranker, rerank_candidates
from src.retrieval import DEFAULT_RETRIEVAL_TOP_K, RetrievalCandidate, retrieve_candidates
from src.validation import MAX_QUESTION_CHARACTERS

MAX_CONTEXT_CANDIDATES = DEFAULT_RERANK_TOP_K
UNSUPPORTED_ANSWER = "I could not find enough evidence to answer that from the selected documents."
UNVERIFIED_ANSWER = "I could not provide a verified answer from the selected documents."


class AnswerGenerator(Protocol):
    def generate(
        self,
        question: str,
        candidates: Sequence[RetrievalCandidate],
        model_id: str,
    ) -> GenerationResult: ...


@dataclass(frozen=True)
class AnswerOutcome:
    status: Literal["ANSWERED", "INSUFFICIENT_CONTEXT"]
    answer: str
    sources: list[VerifiedSource]
    generation_model_id: str | None
    retrieved_candidate_count: int
    reranker_used: bool
    evidence_reason: str


def answer_question(
    connection_factory: Callable[[], psycopg.Connection],
    question: str,
    owner_id: str,
    embedding_provider: QueryEmbeddingProvider,
    generator: AnswerGenerator,
    reranker: Reranker | None = None,
    document_ids: Sequence[UUID] | None = None,
    top_k: int = DEFAULT_RETRIEVAL_TOP_K,
    thinking_mode: bool = False,
    min_evidence_similarity: float = EVIDENCE_MIN_COSINE_SIMILARITY,
) -> AnswerOutcome:
    """Answer only after retrieval finds evidence and source IDs validate."""
    question = question.strip()
    if not question:
        raise ValueError("question must not be empty")
    if len(question) > MAX_QUESTION_CHARACTERS:
        raise ValueError("question is too long")

    query_vector = embed_query(question, embedding_provider, BEDROCK_EMBEDDING_MODEL_ID)
    with connection_factory() as connection:
        retrieved = retrieve_candidates(
            connection,
            owner_id,
            query_vector,
            BEDROCK_EMBEDDING_MODEL_ID,
            top_k=top_k,
            document_ids=document_ids,
        )
    evidence = assess_evidence(retrieved, min_evidence_similarity)
    if evidence.status == "INSUFFICIENT_CONTEXT":
        return AnswerOutcome(
            status="INSUFFICIENT_CONTEXT",
            answer=UNSUPPORTED_ANSWER,
            sources=[],
            generation_model_id=None,
            retrieved_candidate_count=len(retrieved),
            reranker_used=False,
            evidence_reason=evidence.reason,
        )

    evidence_candidates = evidence.candidates
    reranker_used = False
    if reranker is not None:
        rerank_result = rerank_candidates(
            question,
            evidence_candidates,
            reranker,
            top_k=MAX_CONTEXT_CANDIDATES,
        )
        selected_candidates = [item.candidate for item in rerank_result.candidates]
        reranker_used = rerank_result.reranked
    else:
        selected_candidates = evidence_candidates[:MAX_CONTEXT_CANDIDATES]

    generation_model_id = BEDROCK_THINKING_MODEL_ID if thinking_mode else BEDROCK_CHAT_MODEL_ID
    generated = generator.generate(question, selected_candidates, generation_model_id)
    try:
        verified = validate_citations(generated.parsed, source_map(selected_candidates))
    except ValueError:
        return AnswerOutcome(
            status="INSUFFICIENT_CONTEXT",
            answer=UNVERIFIED_ANSWER,
            sources=[],
            generation_model_id=generation_model_id,
            retrieved_candidate_count=len(retrieved),
            reranker_used=reranker_used,
            evidence_reason="INVALID_CITATIONS",
        )

    return AnswerOutcome(
        status=verified.status,
        answer=verified.answer,
        sources=verified.sources,
        generation_model_id=generation_model_id,
        retrieved_candidate_count=len(retrieved),
        reranker_used=reranker_used,
        evidence_reason=evidence.reason,
    )
