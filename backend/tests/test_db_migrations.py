"""Database migration checks for an explicitly disposable local database."""

import os
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg.conninfo import conninfo_to_dict

from src.chunk_repository import DocumentNotFoundError, mark_document_ready, upsert_chunks
from src.chunking import DocumentChunk, chunk_pages
from src.config import BEDROCK_EMBEDDING_MODEL_ID
from src.db import apply_schema, connect_database, rollback_schema
from src.extraction import ExtractedPage
from src.ingestion import (
    IngestionAlreadyProcessingError,
    IngestionIds,
    create_job,
    process_job,
)


def test_connection_url_comes_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(ValueError, match="DATABASE_URL is required"):
        connect_database()


def test_schema_constraints_and_rollback(monkeypatch: pytest.MonkeyPatch) -> None:
    database_url = os.getenv("A3_TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("set A3_TEST_DATABASE_URL to an empty disposable pgvector database")

    connection_info = conninfo_to_dict(database_url)
    database_name = connection_info.get("dbname", "")
    database_host = connection_info.get("host", "")
    if not database_name.startswith("a3_test") or database_host not in {
        "localhost",
        "127.0.0.1",
    }:
        pytest.fail("A3_TEST_DATABASE_URL must point to a local database named a3_test*")

    monkeypatch.setenv("DATABASE_URL", database_url)
    connection = connect_database()
    try:
        apply_schema(connection)
        _check_tables(connection)
        job_id, document_id = _insert_job_and_document(connection)
        _check_invalid_owner(connection, job_id)
        _check_chunk_constraints_and_ready_view(connection, document_id)
        _check_chunk_repository(connection, document_id)
        connection.commit()
        _check_ingestion_orchestrator(connection, database_url)
        connection.commit()
        rollback_schema(connection)
        _check_tables_removed(connection)
    finally:
        connection.close()


def _check_tables(connection: psycopg.Connection) -> None:
    rows = connection.execute(
        """
        SELECT tablename FROM pg_tables
        WHERE schemaname = 'public'
          AND tablename IN ('ingestion_jobs', 'documents', 'chunks')
        """
    ).fetchall()
    assert {row[0] for row in rows} == {"ingestion_jobs", "documents", "chunks"}


def _insert_job_and_document(
    connection: psycopg.Connection,
) -> tuple[str, str]:
    job_id = uuid4()
    document_id = uuid4()
    connection.execute(
        "INSERT INTO ingestion_jobs (id, owner_id) VALUES (%s, %s)",
        (job_id, "owner-a"),
    )
    connection.execute(
        """
        INSERT INTO documents (
            id, ingestion_id, owner_id, original_filename, s3_key,
            checksum_sha256, content_type, byte_size, embedding_model
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            document_id,
            job_id,
            "owner-a",
            "sample.txt",
            f"uploads/{document_id}",
            "a" * 64,
            "text/plain",
            12,
            "amazon.titan-embed-text-v2:0",
        ),
    )
    return str(job_id), str(document_id)


def _check_invalid_owner(connection: psycopg.Connection, job_id: str) -> None:
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        with connection.transaction():
            connection.execute(
                """
                INSERT INTO documents (
                    id, ingestion_id, owner_id, original_filename, s3_key,
                    checksum_sha256, content_type, byte_size, embedding_model
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    uuid4(),
                    job_id,
                    "owner-b",
                    "wrong-owner.txt",
                    "uploads/wrong-owner",
                    "b" * 64,
                    "text/plain",
                    12,
                    "amazon.titan-embed-text-v2:0",
                ),
            )


def _check_chunk_constraints_and_ready_view(
    connection: psycopg.Connection,
    document_id: str,
) -> None:
    vector_text = "[" + ",".join("0" for _ in range(1024)) + "]"
    chunk_id = uuid4()
    chunk_values = (
        chunk_id,
        document_id,
        0,
        "A sample text chunk.",
        vector_text,
        "v1",
    )
    insert_chunk = """
        INSERT INTO chunks (id, document_id, ordinal, content, embedding, chunker_version)
        VALUES (%s, %s, %s, %s, %s::vector, %s)
    """
    connection.execute(insert_chunk, chunk_values)
    assert (
        connection.execute(
            "SELECT count(*) FROM ready_chunks WHERE document_id = %s", (document_id,)
        ).fetchone()[0]
        == 0
    )

    connection.execute("UPDATE documents SET status = 'READY' WHERE id = %s", (document_id,))
    assert (
        connection.execute(
            "SELECT count(*) FROM ready_chunks WHERE document_id = %s", (document_id,)
        ).fetchone()[0]
        == 1
    )

    with pytest.raises(psycopg.errors.UniqueViolation):
        with connection.transaction():
            connection.execute(insert_chunk, (uuid4(), *chunk_values[1:]))

    with pytest.raises(psycopg.errors.CheckViolation):
        with connection.transaction():
            connection.execute("UPDATE documents SET status = 'DONE' WHERE id = %s", (document_id,))

    with pytest.raises(psycopg.errors.DataException):
        with connection.transaction():
            connection.execute(
                """
                INSERT INTO chunks (
                    id, document_id, ordinal, content, embedding, chunker_version
                ) VALUES (%s, %s, %s, %s, %s::vector, %s)
                """,
                (uuid4(), document_id, 1, "wrong dimension", "[0,0,0]", "v1"),
            )


def _check_tables_removed(connection: psycopg.Connection) -> None:
    rows = connection.execute(
        """
        SELECT tablename FROM pg_tables
        WHERE schemaname = 'public'
          AND tablename IN ('ingestion_jobs', 'documents', 'chunks')
        """
    ).fetchall()
    assert rows == []


def _check_chunk_repository(connection: psycopg.Connection, document_id: str) -> None:
    document_uuid = UUID(document_id)
    chunks = chunk_pages(
        [ExtractedPage(page_number=1, text="abcdef", start_offset=0, end_offset=6)],
        document_uuid,
        chunk_size=4,
        overlap=1,
    )
    vectors = [[0.01] * 1024 for _ in chunks]

    upsert_chunks(connection, "owner-a", document_uuid, chunks, vectors, "v1")
    upsert_chunks(connection, "owner-a", document_uuid, chunks, vectors, "v1")
    assert _chunk_count(connection, document_uuid) == 2
    assert _ready_chunk_count(connection, document_uuid) == 0

    with pytest.raises(DocumentNotFoundError):
        upsert_chunks(connection, "owner-b", document_uuid, chunks, vectors, "v1")

    invalid_chunk = DocumentChunk(
        chunk_id=uuid4(),
        document_id=document_uuid,
        ordinal=0,
        page_number=0,
        start_offset=0,
        end_offset=4,
        content="new text",
    )
    with pytest.raises(psycopg.errors.CheckViolation):
        upsert_chunks(
            connection,
            "owner-a",
            document_uuid,
            [invalid_chunk],
            [[0.02] * 1024],
            "v2",
        )
    assert _chunk_count(connection, document_uuid) == 2
    assert _ready_chunk_count(connection, document_uuid) == 0

    assert not mark_document_ready(connection, "owner-b", document_uuid, 2)
    assert not mark_document_ready(connection, "owner-a", document_uuid, 3)
    assert mark_document_ready(connection, "owner-a", document_uuid, 2)
    assert _ready_chunk_count(connection, document_uuid) == 2


def _chunk_count(connection: psycopg.Connection, document_id: UUID) -> int:
    return connection.execute(
        "SELECT count(*) FROM chunks WHERE document_id = %s", (document_id,)
    ).fetchone()[0]


def _ready_chunk_count(connection: psycopg.Connection, document_id: UUID) -> int:
    return connection.execute(
        "SELECT count(*) FROM ready_chunks WHERE document_id = %s", (document_id,)
    ).fetchone()[0]


class FakeDocumentStore:
    def __init__(self) -> None:
        self.content_by_document: dict[UUID, bytes] = {}

    def get_document(self, owner_id: str, document_id: UUID) -> bytes:
        assert owner_id == "owner-a"
        return self.content_by_document[document_id]


class FakeEmbeddingProvider:
    def __init__(self, fail_once: bool = False) -> None:
        self.model_id = BEDROCK_EMBEDDING_MODEL_ID
        self.calls = 0
        self.fail_once = fail_once

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        self.calls += 1
        if self.fail_once:
            self.fail_once = False
            raise RuntimeError("provider secret detail must not be persisted")
        return [[0.25] * 1024 for _ in texts]


def _check_ingestion_orchestrator(
    connection: psycopg.Connection,
    database_url: str,
) -> None:
    store = FakeDocumentStore()
    successful_job = _create_text_job(connection, "pipeline.txt")
    store.content_by_document[successful_job.document_id] = b"A fact for the test corpus."
    connection.commit()

    successful_embedder = FakeEmbeddingProvider()

    def connection_factory() -> psycopg.Connection:
        return connect_database(database_url)

    result = process_job(
        connection_factory, store, successful_embedder, "owner-a", successful_job.job_id
    )
    assert result.status == "COMPLETED"
    assert result.chunk_count == 1
    assert successful_embedder.calls == 1

    retry_result = process_job(
        connection_factory, store, successful_embedder, "owner-a", successful_job.job_id
    )
    assert retry_result.status == "COMPLETED"
    assert successful_embedder.calls == 1

    busy_job = _create_text_job(connection, "busy.txt")
    connection.commit()
    with connection_factory() as busy_connection:
        busy_connection.execute(
            "UPDATE ingestion_jobs SET status = 'PROCESSING' WHERE id = %s",
            (busy_job.job_id,),
        )
    busy_embedder = FakeEmbeddingProvider()
    with pytest.raises(IngestionAlreadyProcessingError):
        process_job(connection_factory, store, busy_embedder, "owner-a", busy_job.job_id)
    assert busy_embedder.calls == 0

    retry_job = _create_text_job(connection, "retry.txt")
    store.content_by_document[retry_job.document_id] = b"A fact for the test corpus."
    connection.commit()
    retrying_embedder = FakeEmbeddingProvider(fail_once=True)

    failed = process_job(connection_factory, store, retrying_embedder, "owner-a", retry_job.job_id)
    assert failed.status == "FAILED"
    assert failed.error == "Ingestion failed during embedding"

    with connection_factory() as check_connection:
        status, sanitized_error = check_connection.execute(
            "SELECT status, sanitized_error FROM ingestion_jobs WHERE id = %s",
            (retry_job.job_id,),
        ).fetchone()
        document_status = check_connection.execute(
            "SELECT status FROM documents WHERE id = %s", (retry_job.document_id,)
        ).fetchone()[0]
        ready_count = _ready_chunk_count(check_connection, retry_job.document_id)
    assert status == "FAILED"
    assert sanitized_error == "Ingestion failed during embedding"
    assert document_status == "FAILED"
    assert ready_count == 0

    retried = process_job(connection_factory, store, retrying_embedder, "owner-a", retry_job.job_id)
    assert retried.status == "COMPLETED"
    assert retrying_embedder.calls == 2


def _create_text_job(connection: psycopg.Connection, filename: str) -> IngestionIds:
    data = b"A fact for the test corpus."
    return create_job(
        connection,
        owner_id="owner-a",
        original_filename=filename,
        s3_key=f"documents/owner-a/{uuid4()}",
        checksum_sha256="c" * 64,
        content_type="text/plain",
        byte_size=len(data),
    )
