"""Keep one database record for each uploaded document."""

from uuid import UUID

import boto3
from sqlalchemy import text

from src import config
from src.auth import get_engine


def create_documents_table() -> None:
    with get_engine().begin() as connection:
        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS uploaded_documents (
                id UUID PRIMARY KEY,
                user_id UUID NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
                filename TEXT NOT NULL,
                s3_bucket TEXT,
                s3_key TEXT,
                chunk_count INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'INDEXED',
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """))
        connection.execute(text("""
            CREATE INDEX IF NOT EXISTS uploaded_documents_user_created_idx
            ON uploaded_documents (user_id, created_at DESC)
        """))
        has_vectors = connection.scalar(
            text("SELECT to_regclass('langchain_pg_embedding') IS NOT NULL")
        )
        if has_vectors:
            connection.execute(
                text("""
                    INSERT INTO uploaded_documents
                        (id, user_id, filename, s3_bucket, s3_key, chunk_count)
                    SELECT
                        CASE WHEN langchain_pg_embedding.cmetadata->>'document_id' ~*
                                  '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
                             THEN (langchain_pg_embedding.cmetadata->>'document_id')::uuid END,
                        CASE WHEN langchain_pg_embedding.cmetadata->>'user_id' ~*
                                  '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
                             THEN (langchain_pg_embedding.cmetadata->>'user_id')::uuid END,
                        max(langchain_pg_embedding.cmetadata->>'source'),
                        CASE WHEN max(langchain_pg_embedding.cmetadata->>'s3_key') IS NOT NULL
                             THEN :bucket ELSE NULL END,
                        max(langchain_pg_embedding.cmetadata->>'s3_key'),
                        count(DISTINCT langchain_pg_embedding.cmetadata->>'chunk_index')::integer
                    FROM langchain_pg_embedding
                    JOIN langchain_pg_collection
                      ON langchain_pg_collection.uuid = langchain_pg_embedding.collection_id
                    WHERE langchain_pg_embedding.cmetadata ? 'document_id'
                      AND langchain_pg_embedding.cmetadata ? 'user_id'
                      AND langchain_pg_embedding.cmetadata ? 'source'
                      AND langchain_pg_collection.name = :collection_name
                      AND langchain_pg_embedding.cmetadata->>'document_id' ~*
                          '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
                      AND langchain_pg_embedding.cmetadata->>'user_id' ~*
                          '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
                    GROUP BY langchain_pg_embedding.cmetadata->>'document_id',
                             langchain_pg_embedding.cmetadata->>'user_id'
                    ON CONFLICT (id) DO NOTHING
                """),
                {
                    "bucket": config.S3_BUCKET or None,
                    "collection_name": config.COLLECTION_NAME,
                },
            )


def save_document(
    document_id: str, user_id: str, filename: str, s3_key: str | None, chunk_count: int
) -> None:
    with get_engine().begin() as connection:
        connection.execute(
            text("""
                INSERT INTO uploaded_documents
                    (id, user_id, filename, s3_bucket, s3_key, chunk_count)
                VALUES (:id, :user_id, :filename, :bucket, :s3_key, :chunk_count)
            """),
            {
                "id": UUID(document_id),
                "user_id": UUID(user_id),
                "filename": filename,
                "bucket": config.S3_BUCKET or None,
                "s3_key": s3_key,
                "chunk_count": chunk_count,
            },
        )


def list_documents(user_id: str) -> list[dict]:
    with get_engine().connect() as connection:
        rows = connection.execute(
            text("""
                SELECT id, filename, s3_bucket, s3_key, chunk_count, status, created_at
                FROM uploaded_documents
                WHERE user_id = :user_id
                ORDER BY created_at DESC
            """),
            {"user_id": UUID(user_id)},
        ).mappings().all()
    return [
        {"document_id": str(row["id"]), "source": row["filename"],
         "s3_bucket": row["s3_bucket"], "s3_key": row["s3_key"],
         "chunk_count": row["chunk_count"], "status": row["status"],
         "created_at": row["created_at"]}
        for row in rows
    ]


def delete_document(document_id: str, user_id: str) -> bool:
    """Delete only a document owned by this user and its stored content."""
    params = {"id": UUID(document_id), "user_id": UUID(user_id)}
    with get_engine().connect() as connection:
        row = connection.execute(
            text("""
                SELECT s3_bucket, s3_key FROM uploaded_documents
                WHERE id = :id AND user_id = :user_id
            """),
            params,
        ).mappings().first()
    if row is None:
        return False

    if row["s3_bucket"] and row["s3_key"]:
        boto3.client("s3", region_name=config.AWS_REGION).delete_object(
            Bucket=row["s3_bucket"], Key=row["s3_key"]
        )

    with get_engine().begin() as connection:
        connection.execute(
            text("""
                DELETE FROM langchain_pg_embedding
                WHERE cmetadata->>'user_id' = :user_id_text
                  AND cmetadata->>'document_id' = :document_id_text
            """),
            {"user_id_text": user_id, "document_id_text": document_id},
        )
        connection.execute(
            text("DELETE FROM uploaded_documents WHERE id = :id AND user_id = :user_id"),
            params,
        )
    return True
