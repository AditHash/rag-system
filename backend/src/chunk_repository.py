"""Transactional PostgreSQL writes for document chunks."""

import math
from collections.abc import Sequence
from uuid import UUID

import psycopg

from src.chunking import DocumentChunk
from src.config import BEDROCK_EMBEDDING_DIMENSIONS


class DocumentNotFoundError(LookupError):
    """The document does not exist for the supplied owner."""


def upsert_chunks(
    connection: psycopg.Connection,
    owner_id: str,
    document_id: UUID,
    chunks: Sequence[DocumentChunk],
    embeddings: Sequence[Sequence[float]],
    chunker_version: str,
) -> None:
    """Replace a document's chunks atomically; keep it hidden until marked READY."""
    _validate_inputs(owner_id, document_id, chunks, embeddings, chunker_version)

    with connection.transaction():
        document = connection.execute(
            """
            UPDATE documents SET status = 'PROCESSING', updated_at = now()
            WHERE id = %s AND owner_id = %s
            RETURNING id
            """,
            (document_id, owner_id),
        ).fetchone()
        if document is None:
            raise DocumentNotFoundError("document not found for owner")

        connection.execute("DELETE FROM chunks WHERE document_id = %s", (document_id,))
        with connection.cursor() as cursor:
            cursor.executemany(
                """
            INSERT INTO chunks (
                id, document_id, ordinal, page_number, start_offset, end_offset,
                content, embedding, chunker_version
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s::vector, %s)
                """,
                [
                    (
                        chunk.chunk_id,
                        document_id,
                        chunk.ordinal,
                        chunk.page_number,
                        chunk.start_offset,
                        chunk.end_offset,
                        chunk.content,
                        _vector_text(vector),
                        chunker_version,
                    )
                    for chunk, vector in zip(chunks, embeddings, strict=True)
                ],
            )


def mark_document_ready(
    connection: psycopg.Connection,
    owner_id: str,
    document_id: UUID,
    expected_chunk_count: int,
) -> bool:
    """Expose a processing document only when its expected chunks are all stored."""
    if expected_chunk_count <= 0:
        raise ValueError("expected_chunk_count must be positive")

    with connection.transaction():
        document = connection.execute(
            """
            UPDATE documents AS document
            SET status = 'READY', updated_at = now()
            WHERE document.id = %s
              AND document.owner_id = %s
              AND document.status = 'PROCESSING'
              AND (
                  SELECT count(*) FROM chunks
                  WHERE chunks.document_id = document.id
              ) = %s
            RETURNING document.id
            """,
            (document_id, owner_id, expected_chunk_count),
        ).fetchone()
    return document is not None


def _validate_inputs(
    owner_id: str,
    document_id: UUID,
    chunks: Sequence[DocumentChunk],
    embeddings: Sequence[Sequence[float]],
    chunker_version: str,
) -> None:
    if not owner_id:
        raise ValueError("owner_id is required")
    if not chunks:
        raise ValueError("at least one chunk is required")
    if len(chunks) != len(embeddings):
        raise ValueError("each chunk must have exactly one embedding")
    if not chunker_version:
        raise ValueError("chunker_version is required")
    if any(chunk.document_id != document_id for chunk in chunks):
        raise ValueError("all chunks must belong to the target document")

    for vector in embeddings:
        if len(vector) != BEDROCK_EMBEDDING_DIMENSIONS:
            raise ValueError("embedding dimension does not match the database schema")
        if any(not math.isfinite(value) for value in vector):
            raise ValueError("embedding contains a non-finite value")


def _vector_text(vector: Sequence[float]) -> str:
    """Format pgvector's text representation for an explicit SQL cast."""
    return "[" + ",".join(format(value, ".9g") for value in vector) + "]"
