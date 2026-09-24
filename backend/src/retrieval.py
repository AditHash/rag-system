"""Owner-scoped cosine search over READY PostgreSQL chunks."""

import math
from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

import psycopg

from src.config import BEDROCK_EMBEDDING_DIMENSIONS

DEFAULT_RETRIEVAL_TOP_K = 10
MAX_RETRIEVAL_TOP_K = 20


@dataclass(frozen=True)
class RetrievalCandidate:
    chunk_id: UUID
    document_id: UUID
    original_filename: str
    page_number: int | None
    ordinal: int
    content: str
    cosine_distance: float
    similarity: float


def retrieve_candidates(
    connection: psycopg.Connection,
    owner_id: str,
    query_embedding: Sequence[float],
    expected_model_id: str,
    top_k: int = DEFAULT_RETRIEVAL_TOP_K,
    document_ids: Sequence[UUID] | None = None,
) -> list[RetrievalCandidate]:
    """Return the nearest authorized, READY chunks with source metadata."""
    _validate_search(owner_id, query_embedding, expected_model_id)
    if document_ids is not None and not document_ids:
        return []

    vector_text = _vector_text(query_embedding)
    document_filter = ""
    parameters: list[object] = [vector_text, owner_id, expected_model_id]
    if document_ids is not None:
        document_filter = " AND document.id = ANY(%s)"
        parameters.append(list(document_ids))
    parameters.extend((vector_text, clamp_top_k(top_k)))

    rows = connection.execute(
        f"""
        SELECT chunk.id, document.id, document.original_filename,
               chunk.page_number, chunk.ordinal, chunk.content,
               (chunk.embedding <=> %s::vector) AS cosine_distance
        FROM chunks AS chunk
        JOIN documents AS document ON document.id = chunk.document_id
        WHERE document.owner_id = %s
          AND document.status = 'READY'
          AND document.embedding_model = %s
          {document_filter}
        ORDER BY chunk.embedding <=> %s::vector, chunk.id
        LIMIT %s
        """,
        parameters,
    ).fetchall()

    candidates = []
    for row in rows:
        chunk_id, document_id, filename, page_number, ordinal, content, raw_distance = row
        distance = float(raw_distance)
        candidates.append(
            RetrievalCandidate(
                chunk_id=chunk_id,
                document_id=document_id,
                original_filename=filename,
                page_number=page_number,
                ordinal=ordinal,
                content=content,
                cosine_distance=distance,
                similarity=1.0 - distance,
            )
        )
    return candidates


def clamp_top_k(top_k: int) -> int:
    """Keep requested candidate counts between one and the hard upper bound."""
    return min(max(top_k, 1), MAX_RETRIEVAL_TOP_K)


def _validate_search(
    owner_id: str,
    query_embedding: Sequence[float],
    expected_model_id: str,
) -> None:
    if not owner_id:
        raise ValueError("owner_id is required")
    if not expected_model_id:
        raise ValueError("expected_model_id is required")
    if len(query_embedding) != BEDROCK_EMBEDDING_DIMENSIONS:
        raise ValueError("query embedding dimension does not match the database schema")
    if any(
        not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value)
        for value in query_embedding
    ):
        raise ValueError("query embedding must contain only finite numeric values")


def _vector_text(vector: Sequence[float]) -> str:
    return "[" + ",".join(format(value, ".9g") for value in vector) + "]"
