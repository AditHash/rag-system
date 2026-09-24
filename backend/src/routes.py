"""Versioned HTTP routes for the local ingestion workflow."""

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated, Literal, Protocol
from uuid import UUID, uuid4

import psycopg
from botocore.exceptions import BotoCoreError
from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Request, UploadFile
from pydantic import BaseModel
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from src.auth import verify_api_key
from src.db import connect_database
from src.embedding import BedrockEmbeddingProvider
from src.ingestion import (
    DocumentStore,
    EmbeddingProvider,
    create_job,
    mark_job_failed,
    process_job,
)
from src.job_repository import get_job_status
from src.storage import S3DocumentStore
from src.validation import MAX_UPLOAD_BYTES, validate_upload

MAX_MULTIPART_OVERHEAD_BYTES = 64 * 1024
MAX_INGEST_REQUEST_BYTES = MAX_UPLOAD_BYTES + MAX_MULTIPART_OVERHEAD_BYTES

router = APIRouter()


class UploadStore(DocumentStore, Protocol):
    def key_for_document(self, owner_id: str, document_id: UUID) -> str: ...

    def put_document(
        self, owner_id: str, document_id: UUID, data: bytes, content_type: str
    ) -> str: ...


@dataclass(frozen=True)
class IngestionDependencies:
    store: UploadStore
    embedder: EmbeddingProvider
    connection_factory: Callable[[], psycopg.Connection]


class IngestAcceptedResponse(BaseModel):
    ingestion_id: UUID
    document_ids: list[UUID]
    status: Literal["PENDING"]


class IngestionProgress(BaseModel):
    completed_documents: int
    total_documents: int


class IngestionStatusResponse(BaseModel):
    ingestion_id: UUID
    document_ids: list[UUID]
    status: Literal["PENDING", "PROCESSING", "COMPLETED", "FAILED"]
    stage: str
    progress: IngestionProgress
    error: str | None


class RequestBodyTooLarge(Exception):
    """The full multipart request exceeded the bounded request size."""


class IngestRequestLimitMiddleware:
    """Reject oversized ingestion bodies before FastAPI parses multipart data."""

    def __init__(self, app: ASGIApp, max_bytes: int = MAX_INGEST_REQUEST_BYTES) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] != "http"
            or scope["method"] != "POST"
            or scope["path"] != "/api/v1/ingest"
        ):
            await self.app(scope, receive, send)
            return

        headers = dict(scope["headers"])
        raw_length = headers.get(b"content-length")
        if raw_length is not None:
            try:
                content_length = int(raw_length)
            except ValueError:
                await _send_error(send, 400, "invalid_request", "Request input is invalid")
                return
            if content_length > self.max_bytes:
                await _send_error(
                    send, 413, "file_too_large", "Upload request exceeds the allowed size"
                )
                return

        received_bytes = 0
        request_too_large = False
        response_started = False

        async def limited_receive() -> Message:
            nonlocal received_bytes, request_too_large
            message = await receive()
            if message["type"] == "http.request":
                received_bytes += len(message.get("body", b""))
                if received_bytes > self.max_bytes:
                    request_too_large = True
                    raise RequestBodyTooLarge
            return message

        async def tracked_send(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, tracked_send)
        except Exception:
            if not request_too_large:
                raise
            if not response_started:
                await _send_error(
                    send, 413, "file_too_large", "Upload request exceeds the allowed size"
                )


async def _send_error(send: Send, status_code: int, code: str, message: str) -> None:
    body = json.dumps({"error": {"code": code, "message": message}}).encode()
    await send(
        {
            "type": "http.response.start",
            "status": status_code,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})


def get_ingestion_dependencies(request: Request) -> IngestionDependencies:
    """Create and reuse cloud clients lazily, after an ingestion request arrives."""
    dependencies = getattr(request.app.state, "ingestion_dependencies", None)
    if dependencies is not None:
        return dependencies
    try:
        dependencies = IngestionDependencies(
            store=S3DocumentStore(),
            embedder=BedrockEmbeddingProvider(),
            connection_factory=connect_database,
        )
    except (BotoCoreError, ValueError):
        raise HTTPException(
            status_code=503, detail="Ingestion services are not configured"
        ) from None
    request.app.state.ingestion_dependencies = dependencies
    return dependencies


@router.post(
    "/api/v1/ingest",
    status_code=202,
    response_model=IngestAcceptedResponse,
    tags=["ingestion"],
)
def ingest_document(
    background_tasks: BackgroundTasks,
    file: Annotated[UploadFile, File()],
    owner_id: Annotated[str, Depends(verify_api_key)],
    dependencies: Annotated[IngestionDependencies, Depends(get_ingestion_dependencies)],
) -> IngestAcceptedResponse:
    """Persist a bounded file and schedule its one-document processing job."""
    filename = _safe_filename(file.filename)
    content_type = file.content_type or ""
    data = file.file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File exceeds the 10 MiB limit")
    validate_upload(filename, content_type, data)

    document_id = uuid4()
    job_id = uuid4()
    s3_key = dependencies.store.key_for_document(owner_id, document_id)
    try:
        with dependencies.connection_factory() as connection:
            created = create_job(
                connection,
                owner_id=owner_id,
                original_filename=filename,
                s3_key=s3_key,
                checksum_sha256=hashlib.sha256(data).hexdigest(),
                content_type=content_type,
                byte_size=len(data),
                embedding_model=dependencies.embedder.model_id,
                job_id=job_id,
                document_id=document_id,
            )
    except (psycopg.Error, ValueError):
        raise HTTPException(status_code=503, detail="Ingestion database is unavailable") from None

    try:
        dependencies.store.put_document(owner_id, document_id, data, content_type)
    except Exception:
        mark_job_failed(
            dependencies.connection_factory,
            owner_id,
            created.job_id,
            created.document_id,
            "UPLOADING",
        )
        raise HTTPException(status_code=503, detail="Document storage is unavailable") from None

    background_tasks.add_task(
        process_job,
        dependencies.connection_factory,
        dependencies.store,
        dependencies.embedder,
        owner_id,
        created.job_id,
    )
    return IngestAcceptedResponse(
        ingestion_id=created.job_id,
        document_ids=[created.document_id],
        status="PENDING",
    )


@router.get(
    "/api/v1/ingest/{ingestion_id}/status",
    response_model=IngestionStatusResponse,
    tags=["ingestion"],
)
def read_ingestion_status(
    ingestion_id: UUID,
    owner_id: Annotated[str, Depends(verify_api_key)],
    dependencies: Annotated[IngestionDependencies, Depends(get_ingestion_dependencies)],
) -> IngestionStatusResponse:
    """Return status only when the job belongs to the authenticated owner."""
    try:
        with dependencies.connection_factory() as connection:
            job = get_job_status(connection, owner_id, ingestion_id)
    except psycopg.Error:
        raise HTTPException(status_code=503, detail="Ingestion database is unavailable") from None
    if job is None:
        raise HTTPException(status_code=404, detail="Ingestion job not found")
    return IngestionStatusResponse(
        ingestion_id=job.ingestion_id,
        document_ids=job.document_ids,
        status=job.status,
        stage=job.stage,
        progress=IngestionProgress(
            completed_documents=job.completed_documents,
            total_documents=job.total_documents,
        ),
        error=job.error,
    )


def _safe_filename(filename: str | None) -> str:
    if not filename:
        raise HTTPException(status_code=422, detail="A filename is required")
    normalized = filename.replace("\\", "/").rsplit("/", maxsplit=1)[-1]
    if not normalized or len(normalized) > 255:
        raise HTTPException(status_code=422, detail="Filename is invalid")
    return normalized
