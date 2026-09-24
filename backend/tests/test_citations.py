"""Citation validation binds model-selected IDs to server retrieval records."""

from uuid import uuid4

import pytest

from src.citations import CitationValidationError, source_map, validate_citations
from src.generation import ParsedAnswer
from src.retrieval import RetrievalCandidate


def _candidate(filename: str, page: int | None, start: int, text: str):
    return RetrievalCandidate(
        chunk_id=uuid4(),
        document_id=uuid4(),
        original_filename=filename,
        page_number=page,
        ordinal=0,
        content=text,
        cosine_distance=0.1,
        similarity=0.9,
        start_offset=start,
        end_offset=start + len(text),
    )


def test_valid_multi_source_answer_uses_only_server_metadata() -> None:
    first = _candidate("policy.pdf", 2, 10, "Retention is 30 days.")
    second = _candidate("appendix.txt", None, 4, "Exceptions require approval.")
    mappings = source_map([first, second])
    parsed = ParsedAnswer("ANSWERED", "The policy says 30 days, with exceptions.", ["S2", "S1"])

    answer = validate_citations(parsed, mappings)

    assert answer.status == "ANSWERED"
    assert answer.answer == parsed.answer
    assert [source.source_id for source in answer.sources] == ["S2", "S1"]
    assert answer.sources[0].document_id == second.document_id
    assert answer.sources[0].filename == "appendix.txt"
    assert answer.sources[0].page_number is None
    assert answer.sources[0].start_offset == 4
    assert answer.sources[0].end_offset == 4 + len(second.content)
    assert answer.sources[0].excerpt == second.content
    assert answer.sources[1].filename == "policy.pdf"
    assert answer.sources[1].page_number == 2


def test_refusal_returns_no_sources() -> None:
    parsed = ParsedAnswer("INSUFFICIENT_CONTEXT", "I could not find that in the documents.", [])

    answer = validate_citations(parsed, {})

    assert answer.status == "INSUFFICIENT_CONTEXT"
    assert answer.sources == []


@pytest.mark.parametrize(
    "source_ids, message",
    [([], "at least one"), (["S999"], "unknown"), (["S1", "S1"], "duplicate")],
)
def test_answered_response_rejects_missing_unknown_and_duplicate_ids(
    source_ids: list[str], message: str
) -> None:
    parsed = ParsedAnswer("ANSWERED", "An answer.", source_ids)

    with pytest.raises(CitationValidationError, match=message):
        validate_citations(parsed, source_map([_candidate("source.pdf", 1, 0, "evidence")]))


def test_refusal_with_citation_is_rejected() -> None:
    parsed = ParsedAnswer("INSUFFICIENT_CONTEXT", "No evidence.", ["S1"])

    with pytest.raises(CitationValidationError, match="refusal"):
        validate_citations(parsed, source_map([_candidate("source.pdf", 1, 0, "evidence")]))


def test_invalid_source_id_type_is_rejected() -> None:
    parsed = ParsedAnswer("ANSWERED", "An answer.", [None])  # type: ignore[list-item]

    with pytest.raises(CitationValidationError, match="invalid source ID"):
        validate_citations(parsed, {})
