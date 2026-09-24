"""Database-independent guards run before chunk writes begin."""

from uuid import uuid4

import pytest

from src.chunk_repository import upsert_chunks
from src.chunking import chunk_pages
from src.config import BEDROCK_EMBEDDING_DIMENSIONS
from src.extraction import ExtractedPage


def test_upsert_rejects_mismatched_embedding_count_before_database_access() -> None:
    document_id = uuid4()
    chunks = chunk_pages(
        [ExtractedPage(page_number=1, text="text", start_offset=0, end_offset=4)],
        document_id,
    )

    with pytest.raises(ValueError, match="exactly one embedding"):
        upsert_chunks(None, "owner", document_id, chunks, [], "v1")  # type: ignore[arg-type]


def test_upsert_rejects_wrong_vector_dimension_before_database_access() -> None:
    document_id = uuid4()
    chunks = chunk_pages(
        [ExtractedPage(page_number=1, text="text", start_offset=0, end_offset=4)],
        document_id,
    )

    with pytest.raises(ValueError, match="dimension"):
        upsert_chunks(
            None,
            "owner",
            document_id,
            chunks,
            [[0.0] * (BEDROCK_EMBEDDING_DIMENSIONS - 1)],
            "v1",
        )  # type: ignore[arg-type]
