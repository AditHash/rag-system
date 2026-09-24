"""Pre-generation evidence gate tests use fixed retrieval candidates."""

from uuid import uuid4

import pytest

from src.evidence import assess_evidence
from src.retrieval import RetrievalCandidate


def _candidate(similarity: float, ordinal: int = 0) -> RetrievalCandidate:
    return RetrievalCandidate(
        chunk_id=uuid4(),
        document_id=uuid4(),
        original_filename="source.txt",
        page_number=1,
        ordinal=ordinal,
        content="A source excerpt with a fact.",
        cosine_distance=1.0 - similarity,
        similarity=similarity,
    )


def test_empty_or_weak_evidence_refuses_before_generation() -> None:
    empty = assess_evidence([])
    weak = assess_evidence([_candidate(0.2)])

    assert empty.status == "INSUFFICIENT_CONTEXT"
    assert empty.reason == "NO_CANDIDATES"
    assert empty.max_similarity is None
    assert weak.status == "INSUFFICIENT_CONTEXT"
    assert weak.reason == "BELOW_THRESHOLD"
    assert weak.candidates == []
    assert weak.max_similarity == 0.2


def test_candidate_at_threshold_is_passed_to_generation() -> None:
    candidate = _candidate(0.55)

    decision = assess_evidence([candidate], min_similarity=0.55)

    assert decision.status == "EVIDENCE_FOUND"
    assert decision.reason == "SIMILARITY_THRESHOLD_MET"
    assert decision.candidates == [candidate]


def test_only_candidates_above_threshold_are_selected() -> None:
    weak = _candidate(0.3, ordinal=0)
    strong = _candidate(0.8, ordinal=1)

    decision = assess_evidence([weak, strong], min_similarity=0.55)

    assert decision.status == "EVIDENCE_FOUND"
    assert decision.candidates == [strong]
    assert decision.max_similarity == 0.8


@pytest.mark.parametrize("threshold", [-1.1, 1.1, float("nan")])
def test_invalid_threshold_is_rejected(threshold: float) -> None:
    with pytest.raises(ValueError, match="minimum cosine similarity"):
        assess_evidence([_candidate(0.6)], min_similarity=threshold)


def test_nonfinite_or_out_of_range_candidate_score_is_rejected() -> None:
    with pytest.raises(ValueError, match="candidate similarity"):
        assess_evidence([_candidate(float("nan"))])
