"""Chunk size, overlap, stable ID, and source metadata checks."""

from uuid import uuid4

import pytest

from src.chunking import DocumentChunk, chunk_pages
from src.extraction import ExtractedPage


def test_chunks_respect_size_overlap_and_offsets() -> None:
    document_id = uuid4()
    page = ExtractedPage(page_number=2, text="0123456789ABCDEFGHIJ", start_offset=0, end_offset=20)

    chunks = chunk_pages([page], document_id, chunk_size=10, overlap=2)

    assert [chunk.content for chunk in chunks] == ["0123456789", "89ABCDEFGH", "GHIJ"]
    assert [(chunk.start_offset, chunk.end_offset) for chunk in chunks] == [
        (0, 10),
        (8, 18),
        (16, 20),
    ]
    assert [chunk.ordinal for chunk in chunks] == [0, 1, 2]
    assert all(chunk.page_number == 2 for chunk in chunks)
    assert all(chunk.document_id == document_id for chunk in chunks)
    assert all(isinstance(chunk, DocumentChunk) for chunk in chunks)


def test_recursive_splitter_prefers_paragraph_boundary_and_keeps_absolute_offsets() -> None:
    document_id = uuid4()
    source_text = "First paragraph.\n\nSecond paragraph.\n\nThird paragraph."
    page = ExtractedPage(
        page_number=4,
        text=source_text,
        start_offset=100,
        end_offset=100 + len(source_text),
    )

    chunks = chunk_pages([page], document_id, chunk_size=25, overlap=0)

    assert len(chunks) >= 2
    assert all(chunk.page_number == 4 for chunk in chunks)
    for chunk in chunks:
        relative_start = chunk.start_offset - page.start_offset
        relative_end = chunk.end_offset - page.start_offset
        assert page.text[relative_start:relative_end] == chunk.content
        assert len(chunk.content) <= 25
    assert chunks[0].content == "First paragraph."


def test_chunk_ids_are_repeatable_but_scoped_to_document() -> None:
    page = ExtractedPage(page_number=None, text="small text", start_offset=0, end_offset=10)
    first_document = uuid4()
    second_document = uuid4()

    first = chunk_pages([page], first_document, chunk_size=5, overlap=1)
    repeated = chunk_pages([page], first_document, chunk_size=5, overlap=1)
    other_document = chunk_pages([page], second_document, chunk_size=5, overlap=1)

    assert [chunk.chunk_id for chunk in first] == [chunk.chunk_id for chunk in repeated]
    assert [chunk.chunk_id for chunk in first] != [chunk.chunk_id for chunk in other_document]
    assert all(chunk.page_number is None for chunk in first)


def test_blank_pages_are_skipped_without_shifting_source_page_numbers() -> None:
    document_id = uuid4()
    pages = [
        ExtractedPage(page_number=1, text="   ", start_offset=0, end_offset=3),
        ExtractedPage(page_number=2, text="visible", start_offset=0, end_offset=7),
    ]

    chunks = chunk_pages(pages, document_id)

    assert len(chunks) == 1
    assert chunks[0].page_number == 2
    assert chunks[0].content == "visible"


@pytest.mark.parametrize(
    ("chunk_size", "overlap"),
    [(0, 0), (10_001, 0), (10, -1), (10, 6)],
)
def test_invalid_chunk_settings_are_rejected(chunk_size: int, overlap: int) -> None:
    with pytest.raises(ValueError):
        chunk_pages([], uuid4(), chunk_size=chunk_size, overlap=overlap)


def test_invalid_page_offsets_are_rejected() -> None:
    page = ExtractedPage(page_number=1, text="bad", start_offset=2, end_offset=4)
    with pytest.raises(ValueError, match="offsets"):
        chunk_pages([page], uuid4())
