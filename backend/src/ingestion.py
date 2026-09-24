"""Small ingestion service that connects storage, extraction, embedding, and PostgreSQL."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal, Protocol
from uuid import UUID, uuid4

import psycopg

from src.chunk_repository import mark_document_ready, upsert_chunks
from src.chunking import chunk_pages
from src.config import BEDROCK_EMBEDDING_MODEL_ID
from src.extraction import extract_pdf_pages, extract_txt


class DocumentStore(Protocol):
    """Storage operation required by ingestion."""

    def get_document(self, owner_id: str, document_id: UUID) -> bytes: ...


class EmbeddingProvider(Protocol):
    """Embedding operation and model identity required by ingestion."""

    model_id: str

    def embed_texts(self, texts: list[str]) -> list[list[float]]: ...


class IngestionAlreadyProcessingError(RuntimeError):
    """A worker already owns this job, so a duplicate invocation is rejected."""


@dataclass(frozen=True)
class IngestionIds:
    job_id: UUID
    document_id: UUID


@dataclass(frozen=True)
class IngestionResult:
    status: Literal["COMPLETED", "FAILED"]
    chunk_count: int
    error: str | None = None


def create_job(
    connection: psycopg.Connection,
    owner_id: str,
    original_filename: str,
    s3_key: str,
    checksum_sha256: str,
    content_type: str,
    byte_size: int,
    embedding_model: str = BEDROCK_EMBEDDING_MODEL_ID,
) -> IngestionIds:
    """Persist one pending job and its processing document metadata."""
    ids = IngestionIds(job_id=uuid4(), document_id=uuid4())
    with connection.transaction():
        connection.execute(
            """
            INSERT INTO ingestion_jobs (id, owner_id, total_documents)
            VALUES (%s, %s, 1)
            """,
            (ids.job_id, owner_id),
        )
        connection.execute(
            """
            INSERT INTO documents (
                id, ingestion_id, owner_id, original_filename, s3_key,
                checksum_sha256, content_type, byte_size, embedding_model
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                ids.document_id,
                ids.job_id,
                owner_id,
                original_filename,
                s3_key,
                checksum_sha256,
                content_type,
                byte_size,
                embedding_model,
            ),
        )
    return ids


def process_job(
    connection_factory: Callable[[], psycopg.Connection],
    store: DocumentStore,
    embedder: EmbeddingProvider,
    owner_id: str,
    job_id: UUID,
) -> IngestionResult:
    """Process one persisted job and atomically publish its completed chunks."""
    job_status, document_id, content_type, expected_model = _load_job(
        connection_factory, owner_id, job_id
    )
    if job_status == "COMPLETED":
        return IngestionResult("COMPLETED", _count_chunks(connection_factory, document_id))
    if job_status == "PROCESSING":
        raise IngestionAlreadyProcessingError("ingestion job is already processing")

    stage = "DOWNLOADING"
    if not _claim_job(connection_factory, owner_id, job_id):
        return IngestionResult("COMPLETED", _count_chunks(connection_factory, document_id))
    try:
        data = store.get_document(owner_id, document_id)
        stage = "EXTRACTING"
        _set_stage(connection_factory, owner_id, job_id, stage)
        if content_type == "application/pdf":
            pages = extract_pdf_pages(data)
        elif content_type == "text/plain":
            pages = extract_txt(data)
        else:
            raise ValueError("unsupported stored content type")

        stage = "CHUNKING"
        _set_stage(connection_factory, owner_id, job_id, stage)
        chunks = chunk_pages(pages, document_id)
        if not chunks:
            raise ValueError("document produced no chunks")

        stage = "EMBEDDING"
        _set_stage(connection_factory, owner_id, job_id, stage)
        if embedder.model_id != expected_model:
            raise ValueError("embedding model differs from the model recorded for the document")
        vectors = embedder.embed_texts([chunk.content for chunk in chunks])

        stage = "PERSISTING"
        _set_stage(connection_factory, owner_id, job_id, stage)
        with connection_factory() as connection:
            with connection.transaction():
                upsert_chunks(connection, owner_id, document_id, chunks, vectors, "char-v1")
                if not mark_document_ready(connection, owner_id, document_id, len(chunks)):
                    raise RuntimeError("document could not be marked READY")
                connection.execute(
                    """
                    UPDATE ingestion_jobs
                    SET status = 'COMPLETED', stage = 'COMPLETED',
                        completed_documents = 1, sanitized_error = NULL, updated_at = now()
                    WHERE id = %s AND owner_id = %s
                    """,
                    (job_id, owner_id),
                )
        return IngestionResult("COMPLETED", len(chunks))
    except Exception:
        _mark_failed(connection_factory, owner_id, job_id, document_id, stage)
        return IngestionResult("FAILED", 0, f"Ingestion failed during {stage.lower()}")


def _load_job(
    connection_factory: Callable[[], psycopg.Connection], owner_id: str, job_id: UUID
) -> tuple[str, UUID, str, str]:
    with connection_factory() as connection:
        rows = connection.execute(
            """
            SELECT job.status, document.id, document.content_type, document.embedding_model
            FROM ingestion_jobs AS job
            JOIN documents AS document ON document.ingestion_id = job.id
            WHERE job.id = %s AND job.owner_id = %s
            """,
            (job_id, owner_id),
        ).fetchall()
    if len(rows) != 1:
        raise LookupError("ingestion job not found")
    return rows[0]


def _set_stage(
    connection_factory: Callable[[], psycopg.Connection],
    owner_id: str,
    job_id: UUID,
    stage: str,
) -> None:
    with connection_factory() as connection:
        connection.execute(
            """
            UPDATE ingestion_jobs
            SET status = 'PROCESSING', stage = %s, sanitized_error = NULL, updated_at = now()
            WHERE id = %s AND owner_id = %s
            """,
            (stage, job_id, owner_id),
        )


def _claim_job(
    connection_factory: Callable[[], psycopg.Connection],
    owner_id: str,
    job_id: UUID,
) -> bool:
    """Atomically claim a pending/failed job so two workers do not process it."""
    with connection_factory() as connection:
        row = connection.execute(
            """
            UPDATE ingestion_jobs
            SET status = 'PROCESSING', stage = 'DOWNLOADING',
                sanitized_error = NULL, updated_at = now()
            WHERE id = %s AND owner_id = %s AND status IN ('PENDING', 'FAILED')
            RETURNING id
            """,
            (job_id, owner_id),
        ).fetchone()
    if row is not None:
        return True

    with connection_factory() as connection:
        status = connection.execute(
            "SELECT status FROM ingestion_jobs WHERE id = %s AND owner_id = %s",
            (job_id, owner_id),
        ).fetchone()
    if status is not None and status[0] == "COMPLETED":
        return False
    raise IngestionAlreadyProcessingError("ingestion job is already processing")


def _mark_failed(
    connection_factory: Callable[[], psycopg.Connection],
    owner_id: str,
    job_id: UUID,
    document_id: UUID,
    stage: str,
) -> None:
    sanitized_error = f"Ingestion failed during {stage.lower()}"
    with connection_factory() as connection:
        with connection.transaction():
            connection.execute(
                """
                UPDATE documents SET status = 'FAILED', updated_at = now()
                WHERE id = %s AND owner_id = %s
                """,
                (document_id, owner_id),
            )
            connection.execute(
                """
                UPDATE ingestion_jobs
                SET status = 'FAILED', stage = 'FAILED', sanitized_error = %s, updated_at = now()
                WHERE id = %s AND owner_id = %s
                """,
                (sanitized_error, job_id, owner_id),
            )


def _count_chunks(connection_factory: Callable[[], psycopg.Connection], document_id: UUID) -> int:
    with connection_factory() as connection:
        return connection.execute(
            "SELECT count(*) FROM chunks WHERE document_id = %s", (document_id,)
        ).fetchone()[0]
