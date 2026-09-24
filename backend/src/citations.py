"""Bind model-selected source IDs to trusted retrieval metadata."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from src.generation import ParsedAnswer
from src.retrieval import RetrievalCandidate


class CitationValidationError(ValueError):
    """The model returned missing, duplicate, or unknown source IDs."""


@dataclass(frozen=True)
class VerifiedSource:
    source_id: str
    document_id: UUID
    filename: str
    page_number: int | None
    start_offset: int | None
    end_offset: int | None
    excerpt: str


@dataclass(frozen=True)
class VerifiedAnswer:
    status: Literal["ANSWERED", "INSUFFICIENT_CONTEXT"]
    answer: str
    sources: list[VerifiedSource]


def validate_citations(
    parsed_answer: ParsedAnswer,
    candidates_by_source_id: Mapping[str, RetrievalCandidate],
) -> VerifiedAnswer:
    """Validate every cited ID and assemble its metadata from retrieval rows."""
    cited_ids = parsed_answer.cited_source_ids
    if any(not isinstance(source_id, str) or not source_id for source_id in cited_ids):
        raise CitationValidationError("answer contains an invalid source ID")
    if len(set(cited_ids)) != len(cited_ids):
        raise CitationValidationError("answer contains duplicate source IDs")

    if parsed_answer.status == "INSUFFICIENT_CONTEXT":
        if cited_ids:
            raise CitationValidationError("refusal must not cite sources")
        return VerifiedAnswer(parsed_answer.status, parsed_answer.answer, [])

    if not cited_ids:
        raise CitationValidationError("answered response must cite at least one source")
    unknown_ids = [source_id for source_id in cited_ids if source_id not in candidates_by_source_id]
    if unknown_ids:
        raise CitationValidationError("answer contains an unknown source ID")

    sources = [
        _assemble_source(source_id, candidates_by_source_id[source_id]) for source_id in cited_ids
    ]
    return VerifiedAnswer(parsed_answer.status, parsed_answer.answer, sources)


def source_map(candidates: Sequence[RetrievalCandidate]) -> dict[str, RetrievalCandidate]:
    """Recreate the source IDs assigned in the grounded prompt."""
    return {f"S{index}": candidate for index, candidate in enumerate(candidates, start=1)}


def _assemble_source(source_id: str, candidate: RetrievalCandidate) -> VerifiedSource:
    return VerifiedSource(
        source_id=source_id,
        document_id=candidate.document_id,
        filename=candidate.original_filename,
        page_number=candidate.page_number,
        start_offset=candidate.start_offset,
        end_offset=candidate.end_offset,
        excerpt=candidate.content,
    )
