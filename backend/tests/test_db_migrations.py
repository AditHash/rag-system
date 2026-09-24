"""Database migration checks for an explicitly disposable local database."""

import os
from uuid import uuid4

import psycopg
import pytest
from psycopg.conninfo import conninfo_to_dict

from src.db import apply_schema, connect_database, rollback_schema


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
