"""Metrics for manually reviewed RAG evaluation runs."""

from collections.abc import Sequence
from typing import Any


def summarize_results(results: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Summarize measured records without inventing missing human ratings."""
    if not results:
        raise ValueError("at least one evaluation result is required")

    answerable = [row for row in results if row["answerable"]]
    expected_evidence_count = sum(len(row["expected_evidence_ids"]) for row in answerable)
    retrieved_evidence_count = sum(
        len(set(row["retrieved_evidence_ids"]) & set(row["expected_evidence_ids"]))
        for row in answerable
    )

    unsupported = [row for row in results if not row["answerable"]]
    refused = [row for row in results if row["status"] == "INSUFFICIENT_CONTEXT"]
    true_refusals = sum(not row["answerable"] for row in refused)
    reviewed = [row for row in answerable if row["answer_correct"] is not None]
    generated = [row for row in results if row["citation_valid"] is not None]
    latencies = sorted(row["latency_ms"] for row in results if row["latency_ms"] is not None)

    return {
        "case_count": len(results),
        "answerable_case_count": len(answerable),
        "unsupported_case_count": len(unsupported),
        "retrieval_recall_at_k": _ratio(retrieved_evidence_count, expected_evidence_count),
        "retrieved_expected_evidence_count": retrieved_evidence_count,
        "expected_evidence_count": expected_evidence_count,
        "refusal_precision": _ratio(true_refusals, len(refused)),
        "refusal_recall": _ratio(true_refusals, len(unsupported)),
        "refusal_count": len(refused),
        "citation_validity": _ratio(
            sum(row["citation_valid"] is True for row in generated), len(generated)
        ),
        "generated_case_count": len(generated),
        "answer_accuracy_manual": _ratio(
            sum(row["answer_correct"] is True for row in reviewed), len(reviewed)
        ),
        "manually_reviewed_answerable_count": len(reviewed),
        "mean_latency_ms": _mean(latencies),
        "p95_latency_ms": _percentile_95(latencies),
        "logical_model_requests": {
            name: sum(row["logical_model_requests"].get(name, 0) for row in results)
            for name in ("embedding", "generation", "reranking")
        },
        "failure_case_ids": [row["question_id"] for row in results if row["failure_type"]],
    }


def _ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _mean(values: Sequence[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _percentile_95(values: Sequence[float]) -> float | None:
    if not values:
        return None
    index = max(0, (95 * len(values) + 99) // 100 - 1)
    return values[index]
