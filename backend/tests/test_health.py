"""Local HTTP contract checks; no AWS credentials or network needed."""

from unittest.mock import patch

from fastapi.testclient import TestClient

from src.main import create_app


def test_health_contract() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["content-type"] == "application/json"


def test_health_and_ingestion_routes_are_exposed_in_openapi() -> None:
    with TestClient(create_app()) as client:
        schema = client.get("/openapi.json").json()
        assert client.post("/api/v1/chat", json={"question": "hello"}).status_code == 404
    assert set(schema["paths"]) == {
        "/health",
        "/api/v1/ingest",
        "/api/v1/ingest/{ingestion_id}/status",
    }
    assert "200" in schema["paths"]["/health"]["get"]["responses"]
    assert "202" in schema["paths"]["/api/v1/ingest"]["post"]["responses"]
    assert "200" in schema["paths"]["/api/v1/ingest/{ingestion_id}/status"]["get"]["responses"]


def test_main_uses_configured_worker_count(monkeypatch) -> None:
    from main import main

    monkeypatch.setenv("WEB_CONCURRENCY", "2")
    with patch("main.uvicorn.run") as run_server:
        main()

    run_server.assert_called_once_with(
        "src.main:create_app",
        factory=True,
        host="0.0.0.0",
        port=8000,
        workers=2,
        access_log=False,
    )
