"""Metric tests use fixed records and make no provider calls."""

import pytest

from src.evaluation_metrics import summarize_results


def _record(
    question_id: str,
    answerable: bool,
    expected: list[str],
    retrieved: list[str],
    status: str,
    **overrides: object,
) -> dict:
    row = {
        "question_id": question_id,
        "answerable": answerable,
        "expected_evidence_ids": expected,
        "retrieved_evidence_ids": retrieved,
        "status": status,
        "citation_valid": None,
        "answer_correct": None,
        "latency_ms": 10.0,
        "logical_model_requests": {"embedding": 1, "generation": 0, "reranking": 0},
        "failure_type": None,
    }
    row.update(overrides)
    return row


def test_metrics_compute_recall_refusal_citations_review_and_calls() -> None:
    records = [
        _record(
            "supported",
            True,
            ["a", "b"],
            ["a"],
            "ANSWERED",
            citation_valid=True,
            answer_correct=True,
            latency_ms=10.0,
            logical_model_requests={"embedding": 1, "generation": 1, "reranking": 0},
        ),
        _record("absent", False, [], [], "INSUFFICIENT_CONTEXT", latency_ms=20.0),
        _record("false_refusal", True, ["c"], [], "INSUFFICIENT_CONTEXT", latency_ms=30.0),
    ]

    metrics = summarize_results(records)

    assert metrics["retrieval_recall_at_k"] == pytest.approx(1 / 3)
    assert metrics["refusal_precision"] == pytest.approx(1 / 2)
    assert metrics["refusal_recall"] == 1.0
    assert metrics["citation_validity"] == 1.0
    assert metrics["answer_accuracy_manual"] == 1.0
    assert metrics["mean_latency_ms"] == 20.0
    assert metrics["p95_latency_ms"] == 30.0
    assert metrics["logical_model_requests"] == {
        "embedding": 3,
        "generation": 1,
        "reranking": 0,
    }


def test_empty_results_and_undefined_denominators_are_explicit() -> None:
    with pytest.raises(ValueError, match="at least one"):
        summarize_results([])

    metrics = summarize_results([_record("unreviewed", True, [], [], "INSUFFICIENT_CONTEXT")])
    assert metrics["retrieval_recall_at_k"] is None
    assert metrics["refusal_precision"] == 0.0
    assert metrics["refusal_recall"] is None
    assert metrics["answer_accuracy_manual"] is None
