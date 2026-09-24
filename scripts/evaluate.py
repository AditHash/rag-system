#!/usr/bin/env python3
"""Run the evaluation corpus through the local answer service."""

import argparse
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any
from uuid import UUID

import psycopg

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPOSITORY_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

from src.answering import AnswerOutcome, answer_question
from src.auth import DEMO_OWNER_ID
from src.config import (
    AWS_REGION,
    BEDROCK_CHAT_MODEL_ID,
    BEDROCK_EMBEDDING_MODEL_ID,
    BEDROCK_RERANKER_MODEL_ID,
    BEDROCK_RERANKER_REGION,
    EVIDENCE_MIN_COSINE_SIMILARITY,
)
from src.db import connect_database
from src.embedding import BedrockEmbeddingProvider, EmbeddingProviderError
from src.evaluation_metrics import summarize_results
from src.generation import BedrockGenerator, GenerationError
from src.reranking import BedrockReranker

QUESTIONS_PATH = REPOSITORY_ROOT / "eval" / "questions.jsonl"
EVIDENCE_PATH = REPOSITORY_ROOT / "eval" / "evidence.json"
DEFAULT_RESULTS_PATH = REPOSITORY_ROOT / "eval" / "results.json"
RETRIEVAL_TOP_K = 10


class CountingEmbedder:
    def __init__(self, provider: BedrockEmbeddingProvider) -> None:
        self.provider = provider
        self.model_id = provider.model_id
        self.requests = 0

    def embed_query(self, question: str) -> list[float]:
        self.requests += 1
        return self.provider.embed_query(question)


class CountingGenerator:
    def __init__(self, generator: BedrockGenerator) -> None:
        self.generator = generator
        self.requests = 0

    def generate(self, question: str, candidates: list[Any], model_id: str) -> Any:
        self.requests += 1
        return self.generator.generate(question, candidates, model_id)


class CountingReranker:
    def __init__(self, reranker: BedrockReranker) -> None:
        self.reranker = reranker
        self.model_id = reranker.model_id
        self.requests = 0

    def rerank(self, query: str, candidates: list[Any], number_of_results: int) -> Any:
        self.requests += 1
        return self.reranker.rerank(query, candidates, number_of_results)


def load_corpus() -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    questions = [
        json.loads(line)
        for line in QUESTIONS_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    evidence_data = json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))
    anchors = {}
    for source in evidence_data["sources"]:
        text = (REPOSITORY_ROOT / source["path"]).read_text(encoding="utf-8")
        start, end = _find_anchor(text, source["match_text"])
        anchors[source["id"]] = {**source, "start_offset": start, "end_offset": end}
    return questions, anchors


def _find_anchor(text: str, anchor: str) -> tuple[int, int]:
    pattern = r"\s+".join(re.escape(part) for part in anchor.split())
    match = re.search(pattern, text)
    if match is None:
        raise ValueError("evaluation evidence anchor is missing from its source")
    return match.start(), match.end()


def evidence_ids_for_source(
    filename: str,
    start_offset: int | None,
    end_offset: int | None,
    anchors: dict[str, dict[str, Any]],
) -> list[str]:
    if start_offset is None or end_offset is None:
        return []
    return [
        evidence_id
        for evidence_id, anchor in anchors.items()
        if anchor["upload_filename"] == filename
        and start_offset < anchor["end_offset"]
        and end_offset > anchor["start_offset"]
    ]


def _load_document_ids(source_filenames: list[str]) -> list[UUID]:
    try:
        with connect_database() as connection:
            rows = connection.execute(
                """
                SELECT id, original_filename
                FROM documents
                WHERE owner_id = %s AND status = 'READY'
                  AND original_filename = ANY(%s)
                ORDER BY original_filename, created_at DESC
                """,
                (DEMO_OWNER_ID, source_filenames),
            ).fetchall()
    except psycopg.Error:
        raise ValueError(
            "could not read READY evaluation documents from PostgreSQL"
        ) from None

    by_filename: dict[str, list[UUID]] = {filename: [] for filename in source_filenames}
    for document_id, filename in rows:
        by_filename[filename].append(document_id)
    missing = [filename for filename, ids in by_filename.items() if not ids]
    if missing:
        raise ValueError(
            "upload every evaluation source as a READY document for the demo owner"
        )
    # The query is ordered newest-first, so a repeated fixture upload uses its latest READY copy.
    return [ids[0] for ids in by_filename.values()]


def _manual_answer_rating(question: dict[str, Any], answer: str) -> bool | None:
    print(f"\n{question['id']} Question: {question['question']}")
    print(f"Expected: {question['expected_answer']}")
    print(f"Actual:   {answer}")
    while True:
        rating = (
            input("Is this answer factually correct and supported? [y/n/u]: ")
            .strip()
            .lower()
        )
        if rating in {"y", "n", "u"}:
            return {"y": True, "n": False, "u": None}[rating]
        print("Enter y, n, or u.")


def _source_matches_candidate(source: Any, candidate: Any) -> bool:
    return (
        source.document_id == candidate.document_id
        and source.filename == candidate.original_filename
        and source.page_number == candidate.page_number
        and source.start_offset == candidate.start_offset
        and source.end_offset == candidate.end_offset
        and source.excerpt == candidate.content
    )


def _run_case(
    question: dict[str, Any],
    anchors: dict[str, dict[str, Any]],
    document_ids: list[UUID],
    embedder: CountingEmbedder,
    generator: CountingGenerator,
    reranker: CountingReranker | None,
    manual_review: bool,
) -> dict[str, Any]:
    before_calls = {
        "embedding": embedder.requests,
        "generation": generator.requests,
        "reranking": reranker.requests if reranker else 0,
    }
    started = perf_counter()
    try:
        outcome: AnswerOutcome = answer_question(
            connect_database,
            question["question"],
            DEMO_OWNER_ID,
            embedder,
            generator,
            reranker=reranker,
            document_ids=document_ids,
            top_k=RETRIEVAL_TOP_K,
            thinking_mode=False,
        )
        failure_type = None
    except (
        psycopg.Error,
        EmbeddingProviderError,
        GenerationError,
        ValueError,
    ) as error:
        outcome = None
        failure_type = type(error).__name__
    latency_ms = (perf_counter() - started) * 1000

    current_calls = {
        "embedding": embedder.requests,
        "generation": generator.requests,
        "reranking": reranker.requests if reranker else 0,
    }
    call_counts = {
        name: current_calls[name] - count for name, count in before_calls.items()
    }
    if outcome is None:
        return {
            "question_id": question["id"],
            "answerable": question["answerable"],
            "expected_evidence_ids": question["evidence_ids"],
            "retrieved_evidence_ids": [],
            "cited_evidence_ids": [],
            "status": "ERROR",
            "citation_valid": None,
            "answer_correct": None,
            "latency_ms": latency_ms,
            "logical_model_requests": call_counts,
            "failure_type": failure_type,
        }

    retrieved_ids = sorted(
        {
            evidence_id
            for candidate in outcome.retrieved_candidates
            for evidence_id in evidence_ids_for_source(
                candidate.original_filename,
                candidate.start_offset,
                candidate.end_offset,
                anchors,
            )
        }
    )
    cited_ids = sorted(
        {
            evidence_id
            for source in outcome.sources
            for evidence_id in evidence_ids_for_source(
                source.filename, source.start_offset, source.end_offset, anchors
            )
        }
    )
    citation_valid = None
    if outcome.generation_model_id is not None:
        citation_valid = outcome.evidence_reason != "INVALID_CITATIONS" and all(
            any(
                _source_matches_candidate(source, candidate)
                for candidate in outcome.retrieved_candidates
            )
            for source in outcome.sources
        )
    if not manual_review or not question["answerable"]:
        answer_correct = None
    elif outcome.status != "ANSWERED":
        answer_correct = False
    else:
        answer_correct = _manual_answer_rating(question, outcome.answer)
    return {
        "question_id": question["id"],
        "answerable": question["answerable"],
        "expected_evidence_ids": question["evidence_ids"],
        "retrieved_evidence_ids": retrieved_ids,
        "cited_evidence_ids": cited_ids,
        "status": outcome.status,
        "answer": outcome.answer,
        "generation_model_id": outcome.generation_model_id,
        "citation_valid": citation_valid,
        "answer_correct": answer_correct,
        "latency_ms": latency_ms,
        "logical_model_requests": call_counts,
        "failure_type": failure_type,
    }


def run_evaluation(args: argparse.Namespace) -> None:
    if not args.allow_model_calls:
        raise ValueError(
            "live evaluation requires the explicit --allow-model-calls flag"
        )
    if not args.manual_review:
        raise ValueError("pass --manual-review to record answer correctness honestly")
    if not args.output.parent.exists():
        raise ValueError("output directory does not exist")
    if args.output.exists():
        raise ValueError("results file already exists; choose another --output path")

    questions, anchors = load_corpus()
    filenames = list(
        dict.fromkeys(item["upload_filename"] for item in anchors.values())
    )
    document_ids = _load_document_ids(filenames)

    embedder = CountingEmbedder(BedrockEmbeddingProvider())
    generator = CountingGenerator(BedrockGenerator())
    reranker = CountingReranker(BedrockReranker()) if args.with_reranker else None
    results = []
    for question in questions:
        result = _run_case(
            question,
            anchors,
            document_ids,
            embedder,
            generator,
            reranker,
            args.manual_review,
        )
        results.append(result)
        if result["failure_type"]:
            print(
                f"Stopping after {question['id']} failed ({result['failure_type']}); "
                "not sending further model requests."
            )
            break
    output = {
        "run_at_utc": datetime.now(UTC).isoformat(),
        "run_status": "complete" if len(results) == len(questions) else "partial",
        "dataset_case_count": len(questions),
        "completed_case_count": len(results),
        "models": {
            "embedding": BEDROCK_EMBEDDING_MODEL_ID,
            "generation": BEDROCK_CHAT_MODEL_ID,
            "reranker": BEDROCK_RERANKER_MODEL_ID if args.with_reranker else None,
            "reranker_region": BEDROCK_RERANKER_REGION if args.with_reranker else None,
        },
        "configuration": {
            "aws_region": AWS_REGION,
            "top_k": RETRIEVAL_TOP_K,
            "evidence_min_cosine_similarity": EVIDENCE_MIN_COSINE_SIMILARITY,
            "reranker_enabled": args.with_reranker,
            "answer_correctness_method": "candidate manual rating",
            "owner_scope": DEMO_OWNER_ID,
        },
        "metrics": summarize_results(results),
        "cases": results,
    }
    args.output.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(f"Saved local evaluation results to {args.output}")
    print(json.dumps(output["metrics"], indent=2))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run", action="store_true", help="run against local PostgreSQL and Bedrock"
    )
    parser.add_argument(
        "--allow-model-calls",
        action="store_true",
        help="explicitly allow bounded Bedrock calls for this evaluation",
    )
    parser.add_argument(
        "--manual-review",
        action="store_true",
        help="ask for a manual correctness rating after each generated answer",
    )
    parser.add_argument(
        "--with-reranker",
        action="store_true",
        help="enable Cohere reranking, adding a model call where evidence passes",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_RESULTS_PATH)
    args = parser.parse_args()

    try:
        if args.run:
            run_evaluation(args)
        else:
            questions, anchors = load_corpus()
            print(
                f"Corpus valid: {len(questions)} cases, {len(anchors)} evidence anchors. "
                "No database or model calls made."
            )
    except (OSError, ValueError, KeyError) as error:
        print(f"Evaluation stopped: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
