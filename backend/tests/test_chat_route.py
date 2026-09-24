"""Chat HTTP tests use injected service dependencies and make no AWS calls."""

from contextlib import nullcontext
from uuid import uuid4

import psycopg
from fastapi.testclient import TestClient

from src.answering import AnswerOutcome
from src.citations import VerifiedSource
from src.main import create_app
from src.routes import ChatDependencies, get_chat_dependencies


class FakeEmbedder:
    model_id = "embedding-test"

    def embed_query(self, question: str) -> list[float]:
        raise AssertionError("the HTTP test replaces answer_question")


def _configure_app(monkeypatch):
    monkeypatch.setenv("API_KEY", "test-key")
    app = create_app()
    calls: list[dict[str, object]] = []
    dependencies = ChatDependencies(
        embedder=FakeEmbedder(),
        generator=object(),  # type: ignore[arg-type]
        reranker=None,
        connection_factory=lambda: nullcontext(object()),
    )
    app.dependency_overrides[get_chat_dependencies] = lambda: dependencies
    return app, calls


def test_chat_returns_verified_source_shape_and_passes_scoped_inputs(monkeypatch) -> None:
    app, calls = _configure_app(monkeypatch)
    document_id = uuid4()
    source = VerifiedSource(
        source_id="S1",
        document_id=document_id,
        filename="policy.pdf",
        page_number=2,
        start_offset=12,
        end_offset=40,
        excerpt="The retention period is thirty days.",
    )
    outcome = AnswerOutcome(
        status="ANSWERED",
        answer="The retention period is thirty days.",
        sources=[source],
        generation_model_id="qwen-test",
        retrieved_candidate_count=4,
        reranker_used=False,
        evidence_reason="SIMILARITY_THRESHOLD_MET",
    )

    def answer_stub(connection, question, owner_id, embedder, generator, **kwargs):
        calls.append(
            {
                "connection": connection,
                "question": question,
                "owner_id": owner_id,
                "embedder": embedder,
                "generator": generator,
                **kwargs,
            }
        )
        return outcome

    monkeypatch.setattr("src.routes.answer_question", answer_stub)
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/chat",
            headers={"X-API-Key": "test-key"},
            json={
                "question": "  What is the retention period?  ",
                "document_ids": [str(document_id)],
                "top_k": 8,
                "thinking_mode": True,
            },
        )

    assert response.status_code == 200
    assert response.json() == {
        "status": "ANSWERED",
        "answer": "The retention period is thirty days.",
        "sources": [
            {
                "source_id": "S1",
                "document_id": str(document_id),
                "filename": "policy.pdf",
                "page_number": 2,
                "start_offset": 12,
                "end_offset": 40,
                "excerpt": "The retention period is thirty days.",
            }
        ],
    }
    assert calls[0]["question"] == "What is the retention period?"
    assert calls[0]["owner_id"] == "demo-user"
    assert calls[0]["document_ids"] == [document_id]
    assert calls[0]["top_k"] == 8
    assert calls[0]["thinking_mode"] is True


def test_chat_requires_api_key(monkeypatch) -> None:
    app, _ = _configure_app(monkeypatch)
    with TestClient(app) as client:
        response = client.post("/api/v1/chat", json={"question": "question"})

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


def test_chat_validates_question_top_k_document_scope_and_extra_fields(monkeypatch) -> None:
    app, _ = _configure_app(monkeypatch)
    headers = {"X-API-Key": "test-key"}
    with TestClient(app) as client:
        empty = client.post("/api/v1/chat", headers=headers, json={"question": "  "})
        too_long = client.post("/api/v1/chat", headers=headers, json={"question": "q" * 4_001})
        document_id = uuid4()
        bad_top_k = client.post(
            "/api/v1/chat", headers=headers, json={"question": "x", "top_k": 21}
        )
        duplicate_documents = client.post(
            "/api/v1/chat",
            headers=headers,
            json={"question": "x", "document_ids": [str(document_id), str(document_id)]},
        )
        extra = client.post(
            "/api/v1/chat", headers=headers, json={"question": "x", "unknown": True}
        )

    assert [empty.status_code, too_long.status_code, bad_top_k.status_code] == [422, 422, 422]
    assert duplicate_documents.status_code == 422
    assert extra.status_code == 422
    assert empty.json()["error"]["code"] == "invalid_request"


def test_chat_database_failure_returns_sanitized_service_error(monkeypatch) -> None:
    app, _ = _configure_app(monkeypatch)

    def unavailable(*_args, **_kwargs):
        raise psycopg.OperationalError("private host and password details")

    monkeypatch.setattr("src.routes.answer_question", unavailable)
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/chat",
            headers={"X-API-Key": "test-key"},
            json={"question": "question"},
        )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "service_unavailable"
    assert "password details" not in response.text


def test_chat_insufficient_context_response_has_no_sources(monkeypatch) -> None:
    app, _ = _configure_app(monkeypatch)
    monkeypatch.setattr(
        "src.routes.answer_question",
        lambda *_args, **_kwargs: AnswerOutcome(
            status="INSUFFICIENT_CONTEXT",
            answer="I could not find enough evidence.",
            sources=[],
            generation_model_id=None,
            retrieved_candidate_count=0,
            reranker_used=False,
            evidence_reason="NO_CANDIDATES",
        ),
    )
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/chat",
            headers={"X-API-Key": "test-key"},
            json={"question": "unanswerable"},
        )

    assert response.status_code == 200
    assert response.json()["status"] == "INSUFFICIENT_CONTEXT"
    assert response.json()["sources"] == []
