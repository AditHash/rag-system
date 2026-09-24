"""Retrieval repository tests with a fake connection and fixed vectors."""

from uuid import uuid4

import pytest

from src.config import BEDROCK_EMBEDDING_DIMENSIONS
from src.retrieval import (
    MAX_RETRIEVAL_TOP_K,
    clamp_top_k,
    retrieve_candidates,
)


class FakeCursor:
    def __init__(self, rows):
        self.rows = rows

    def fetchall(self):
        return self.rows


class FakeConnection:
    def __init__(self, rows):
        self.rows = rows
        self.query = ""
        self.parameters = ()

    def execute(self, query, parameters):
        self.query = query
        self.parameters = parameters
        return FakeCursor(self.rows)


def test_retrieve_candidates_returns_metadata_and_cosine_similarity() -> None:
    chunk_id = uuid4()
    document_id = uuid4()
    connection = FakeConnection(
        [(chunk_id, document_id, "guide.pdf", 3, 30, 45, 4, "source excerpt", 0.125)]
    )
    query = [0.0] * BEDROCK_EMBEDDING_DIMENSIONS

    results = retrieve_candidates(connection, "owner-a", query, "embedding-v1")

    assert len(results) == 1
    assert results[0].chunk_id == chunk_id
    assert results[0].document_id == document_id
    assert results[0].original_filename == "guide.pdf"
    assert results[0].page_number == 3
    assert results[0].start_offset == 30
    assert results[0].end_offset == 45
    assert results[0].ordinal == 4
    assert results[0].content == "source excerpt"
    assert results[0].cosine_distance == 0.125
    assert results[0].similarity == 0.875
    assert "document.owner_id = %s" in connection.query
    assert "document.status = 'READY'" in connection.query
    assert "document.embedding_model = %s" in connection.query
    assert "chunk.embedding <=> %s::vector" in connection.query
    assert connection.parameters[1:3] == ["owner-a", "embedding-v1"]
    assert connection.parameters[-1] == 10


def test_retrieve_candidates_filters_optional_document_ids_and_clamps_k() -> None:
    document_id = uuid4()
    connection = FakeConnection([])

    results = retrieve_candidates(
        connection,
        "owner-a",
        [0.0] * BEDROCK_EMBEDDING_DIMENSIONS,
        "embedding-v1",
        top_k=100,
        document_ids=[document_id],
    )

    assert results == []
    assert "document.id = ANY(%s)" in connection.query
    assert connection.parameters[3] == [document_id]
    assert connection.parameters[-1] == MAX_RETRIEVAL_TOP_K


def test_empty_document_filter_returns_no_results_without_query() -> None:
    connection = FakeConnection([])

    results = retrieve_candidates(
        connection,
        "owner-a",
        [0.0] * BEDROCK_EMBEDDING_DIMENSIONS,
        "embedding-v1",
        document_ids=[],
    )

    assert results == []
    assert connection.query == ""


@pytest.mark.parametrize("top_k, expected", [(-2, 1), (0, 1), (3, 3), (100, 20)])
def test_clamp_top_k_bounds_result_count(top_k: int, expected: int) -> None:
    assert clamp_top_k(top_k) == expected


def test_retrieve_candidates_rejects_invalid_query_vector_before_database_call() -> None:
    connection = FakeConnection([])

    with pytest.raises(ValueError, match="dimension"):
        retrieve_candidates(connection, "owner-a", [0.0], "embedding-v1")

    assert connection.query == ""
