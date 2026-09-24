"""HTTP contract tests for uploads use fake database, S3, and Bedrock adapters."""

import asyncio
from contextlib import nullcontext
from uuid import UUID

from fastapi.testclient import TestClient

from src.ingestion import IngestionIds
from src.main import create_app
from src.routes import (
    MAX_INGEST_REQUEST_BYTES,
    IngestionDependencies,
    IngestRequestLimitMiddleware,
    get_ingestion_dependencies,
)


class FakeUploadStore:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.put_call: tuple[str, UUID, bytes, str] | None = None

    def key_for_document(self, owner_id: str, document_id: UUID) -> str:
        return f"documents/{owner_id}/{document_id}"

    def put_document(self, owner_id: str, document_id: UUID, data: bytes, content_type: str) -> str:
        if self.fail:
            raise RuntimeError("private storage error")
        self.put_call = (owner_id, document_id, data, content_type)
        return self.key_for_document(owner_id, document_id)

    def get_document(self, owner_id: str, document_id: UUID) -> bytes:
        raise AssertionError("the HTTP test replaces background processing")


class FakeEmbedder:
    model_id = "embedding-test"

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        raise AssertionError("the HTTP test replaces background processing")


def _configure_app(monkeypatch, store: FakeUploadStore):
    monkeypatch.setenv("API_KEY", "test-key")
    app = create_app()
    background_calls: list[tuple[object, ...]] = []
    job_calls: list[dict[str, object]] = []
    dependencies = IngestionDependencies(
        store=store,
        embedder=FakeEmbedder(),
        connection_factory=lambda: nullcontext(object()),
    )
    app.dependency_overrides[get_ingestion_dependencies] = lambda: dependencies

    def create_job_stub(_connection, **kwargs):
        job_calls.append(kwargs)
        return IngestionIds(job_id=kwargs["job_id"], document_id=kwargs["document_id"])

    monkeypatch.setattr("src.routes.create_job", create_job_stub)
    monkeypatch.setattr("src.routes.process_job", lambda *args: background_calls.append(args))
    monkeypatch.setattr("src.routes.mark_job_failed", lambda *args: None)
    return app, background_calls, job_calls


def test_ingest_accepts_one_valid_file_and_schedules_processing(monkeypatch) -> None:
    store = FakeUploadStore()
    app, background_calls, job_calls = _configure_app(monkeypatch, store)

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/ingest",
            headers={"X-API-Key": "test-key"},
            files={"file": (r"folder\guide.txt", b"Known source text.", "text/plain")},
        )

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "PENDING"
    assert len(body["document_ids"]) == 1
    assert UUID(body["ingestion_id"])
    assert store.put_call is not None
    assert store.put_call[0] == "demo-user"
    assert store.put_call[2:] == (b"Known source text.", "text/plain")
    assert job_calls[0]["original_filename"] == "guide.txt"
    assert job_calls[0]["s3_key"] == store.key_for_document("demo-user", store.put_call[1])
    assert len(background_calls) == 1


def test_ingest_rejects_missing_and_invalid_api_keys(monkeypatch) -> None:
    app, _, _ = _configure_app(monkeypatch, FakeUploadStore())

    with TestClient(app) as client:
        missing = client.post("/api/v1/ingest", files={"file": ("a.txt", b"text", "text/plain")})
        invalid = client.post(
            "/api/v1/ingest",
            headers={"X-API-Key": "wrong"},
            files={"file": ("a.txt", b"text", "text/plain")},
        )

    assert missing.status_code == 401
    assert invalid.status_code == 401
    assert missing.json()["error"]["code"] == "unauthorized"


def test_ingest_rejects_unsupported_and_malformed_documents(monkeypatch) -> None:
    app, _, job_calls = _configure_app(monkeypatch, FakeUploadStore())
    headers = {"X-API-Key": "test-key"}

    with TestClient(app) as client:
        unsupported = client.post(
            "/api/v1/ingest", headers=headers, files={"file": ("image.png", b"data", "image/png")}
        )
        malformed = client.post(
            "/api/v1/ingest",
            headers=headers,
            files={"file": ("bad.pdf", b"not a PDF", "application/pdf")},
        )

    assert unsupported.status_code == 415
    assert malformed.status_code == 422
    assert job_calls == []


def test_ingest_file_and_request_size_limits(monkeypatch) -> None:
    app, _, _ = _configure_app(monkeypatch, FakeUploadStore())
    headers = {"X-API-Key": "test-key"}

    with TestClient(app) as client:
        file_too_large = client.post(
            "/api/v1/ingest",
            headers=headers,
            files={"file": ("large.txt", b"x" * (10 * 1024 * 1024 + 1), "text/plain")},
        )
        request_too_large = client.post(
            "/api/v1/ingest",
            headers=headers,
            files={
                "file": (
                    "larger.txt",
                    b"x" * (MAX_INGEST_REQUEST_BYTES + 1),
                    "text/plain",
                )
            },
        )

    assert file_too_large.status_code == 413
    assert request_too_large.status_code == 413
    assert request_too_large.json()["error"]["code"] == "file_too_large"


def test_storage_failure_marks_job_failed_and_returns_safe_error(monkeypatch) -> None:
    app, background_calls, job_calls = _configure_app(monkeypatch, FakeUploadStore(fail=True))

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/ingest",
            headers={"X-API-Key": "test-key"},
            files={"file": ("a.txt", b"text", "text/plain")},
        )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "service_unavailable"
    assert "private storage error" not in response.text
    assert job_calls
    assert background_calls == []


def test_request_limit_middleware_counts_chunked_body_without_content_length() -> None:
    chunks = [b"123456", b"789012"]
    response_messages = []

    async def receive():
        if chunks:
            return {"type": "http.request", "body": chunks.pop(0), "more_body": bool(chunks)}
        return {"type": "http.request", "body": b"", "more_body": False}

    async def app(_scope, inner_receive, send):
        while (await inner_receive())["more_body"]:
            pass
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    async def send(message):
        response_messages.append(message)

    middleware = IngestRequestLimitMiddleware(app, max_bytes=10)
    asyncio.run(
        middleware(
            {
                "type": "http",
                "method": "POST",
                "path": "/api/v1/ingest",
                "headers": [],
            },
            receive,
            send,
        )
    )

    assert response_messages[0]["status"] == 413
    assert b'"code": "file_too_large"' in response_messages[1]["body"]
