"""Check evaluation cases against their tracked source anchors."""

import json
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
EVALUATION_DIRECTORY = REPOSITORY_ROOT / "eval"


def _load_corpus() -> tuple[list[dict], dict[str, dict]]:
    questions = [
        json.loads(line)
        for line in (EVALUATION_DIRECTORY / "questions.jsonl").read_text().splitlines()
        if line.strip()
    ]
    evidence = json.loads((EVALUATION_DIRECTORY / "evidence.json").read_text())
    return questions, {source["id"]: source for source in evidence["sources"]}


def test_corpus_has_10_to_15_unique_cases_and_required_scenarios() -> None:
    questions, evidence = _load_corpus()
    ids = [item["id"] for item in questions]
    tags = {tag for item in questions for tag in item["tags"]}

    assert 10 <= len(questions) <= 15
    assert len(ids) == len(set(ids))
    assert {"paraphrase", "conflicting_source", "out_of_document", "refusal"} <= tags
    assert all(item["expected_answer"].strip() for item in questions)
    assert all(item["answerable"] == bool(item["evidence_ids"]) for item in questions)
    assert all(
        evidence_id in evidence for item in questions for evidence_id in item["evidence_ids"]
    )


def test_every_evidence_anchor_occurs_in_its_tracked_source() -> None:
    _questions, evidence = _load_corpus()

    for source in evidence.values():
        content = " ".join((REPOSITORY_ROOT / source["path"]).read_text().split())
        anchor = " ".join(source["match_text"].split())
        assert anchor in content, source["id"]
