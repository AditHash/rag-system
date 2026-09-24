"""A pre-generation check that refuses when retrieval returns weak evidence."""

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from src.config import EVIDENCE_MIN_COSINE_SIMILARITY
from src.retrieval import RetrievalCandidate


@dataclass(frozen=True)
class EvidenceDecision:
    status: Literal["EVIDENCE_FOUND", "INSUFFICIENT_CONTEXT"]
    reason: Literal["SIMILARITY_THRESHOLD_MET", "NO_CANDIDATES", "BELOW_THRESHOLD"]
    candidates: list[RetrievalCandidate]
    max_similarity: float | None
    threshold: float


def assess_evidence(
    candidates: Sequence[RetrievalCandidate],
    min_similarity: float = EVIDENCE_MIN_COSINE_SIMILARITY,
) -> EvidenceDecision:
    """Allow generation only when at least one candidate clears the threshold."""
    if not math.isfinite(min_similarity) or not -1.0 <= min_similarity <= 1.0:
        raise ValueError("minimum cosine similarity must be between -1 and 1")
    if not candidates:
        return EvidenceDecision(
            status="INSUFFICIENT_CONTEXT",
            reason="NO_CANDIDATES",
            candidates=[],
            max_similarity=None,
            threshold=min_similarity,
        )

    scores = [candidate.similarity for candidate in candidates]
    if any(not math.isfinite(score) or not -1.0 <= score <= 1.0 for score in scores):
        raise ValueError("candidate similarity must be a finite cosine value")
    max_similarity = max(scores)
    accepted = [candidate for candidate in candidates if candidate.similarity >= min_similarity]
    if not accepted:
        return EvidenceDecision(
            status="INSUFFICIENT_CONTEXT",
            reason="BELOW_THRESHOLD",
            candidates=[],
            max_similarity=max_similarity,
            threshold=min_similarity,
        )
    return EvidenceDecision(
        status="EVIDENCE_FOUND",
        reason="SIMILARITY_THRESHOLD_MET",
        candidates=accepted,
        max_similarity=max_similarity,
        threshold=min_similarity,
    )
