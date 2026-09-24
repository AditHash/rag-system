"""Owner-scoped reads for persisted ingestion job status."""

from dataclasses import dataclass
from uuid import UUID

import psycopg


@dataclass(frozen=True)
class JobStatusRecord:
    ingestion_id: UUID
    document_ids: list[UUID]
    status: str
    stage: str
    completed_documents: int
    total_documents: int
    error: str | None


def get_job_status(
    connection: psycopg.Connection, owner_id: str, ingestion_id: UUID
) -> JobStatusRecord | None:
    """Return a job only when its authenticated owner matches."""
    row = connection.execute(
        """
        SELECT job.id, job.status, job.stage, job.completed_documents,
               job.total_documents, job.sanitized_error,
               COALESCE(array_agg(document.id ORDER BY document.id)
                   FILTER (WHERE document.id IS NOT NULL), '{}') AS document_ids
        FROM ingestion_jobs AS job
        LEFT JOIN documents AS document
          ON document.ingestion_id = job.id AND document.owner_id = job.owner_id
        WHERE job.id = %s AND job.owner_id = %s
        GROUP BY job.id
        """,
        (ingestion_id, owner_id),
    ).fetchone()
    if row is None:
        return None
    job_id, status, stage, completed, total, error, document_ids = row
    return JobStatusRecord(
        ingestion_id=job_id,
        document_ids=document_ids,
        status=status,
        stage=stage,
        completed_documents=completed,
        total_documents=total,
        error=error,
    )
