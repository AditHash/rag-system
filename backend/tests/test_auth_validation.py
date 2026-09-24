"""Local checks for API-key auth, request validation, and error responses."""

import pytest
from fastapi import Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient

from src.auth import DEMO_OWNER_ID, verify_api_key
from src.errors import install_error_handlers
from src.validation import validate_question, validate_upload


def _protected_client() -> TestClient:
    app = FastAPI()
    install_error_handlers(app)

    @app.get("/protected")
    def protected(owner_id: str = Depends(verify_api_key)) -> dict[str, str]:
        return {"owner_id": owner_id}

    return TestClient(app)


def test_api_key_authentication(monkeypatch) -> None:
    monkeypatch.setenv("API_KEY", "local-test-secret")
    with _protected_client() as client:
        valid = client.get("/protected", headers={"X-API-Key": "local-test-secret"})
        missing = client.get("/protected")
        invalid = client.get("/protected", headers={"X-API-Key": "wrong"})

    assert valid.status_code == 200
    assert valid.json() == {"owner_id": DEMO_OWNER_ID}
    assert missing.status_code == 401
    assert invalid.status_code == 401
    assert "local-test-secret" not in invalid.text


def test_missing_server_key_fails_closed(monkeypatch) -> None:
    monkeypatch.delenv("API_KEY", raising=False)
    with _protected_client() as client:
        response = client.get("/protected", headers={"X-API-Key": "some-key"})

    assert response.status_code == 503
    assert response.json() == {
        "error": {"code": "service_unavailable", "message": "Service is not configured"}
    }


def test_question_validation_trims_and_bounds() -> None:
    assert validate_question("  What changed?  ") == "What changed?"
    for question in ("  ", "x" * 4_001):
        with pytest.raises(HTTPException) as error:
            validate_question(question)
        assert error.value.status_code == 422


def test_pdf_and_text_upload_validation() -> None:
    validate_upload("report.PDF", "application/pdf", b"%PDF-1.7\ncontent")
    validate_upload("notes.txt", "text/plain", b"hello\n")

    invalid_uploads = [
        ("empty.txt", "text/plain", b""),
        ("fake.pdf", "application/pdf", b"not a PDF"),
        ("notes.txt", "text/plain", b"\xff"),
        ("blank.txt", "text/plain", b"  \n"),
    ]
    for filename, content_type, data in invalid_uploads:
        with pytest.raises(HTTPException) as error:
            validate_upload(filename, content_type, data)
        assert error.value.status_code in (413, 415, 422)

    with pytest.raises(HTTPException) as error:
        validate_upload("image.png", "image/png", b"data")
    assert error.value.status_code == 415


def test_upload_size_limit() -> None:
    with pytest.raises(HTTPException) as error:
        validate_upload("large.txt", "text/plain", b"x" * (10 * 1024 * 1024 + 1))
    assert error.value.status_code == 413


def test_error_envelope_hides_unexpected_exception_details() -> None:
    app = FastAPI()
    install_error_handlers(app)

    @app.get("/failure")
    def failure() -> None:
        raise RuntimeError("private implementation detail")

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/failure")

    assert response.status_code == 500
    assert response.json() == {
        "error": {"code": "internal_error", "message": "An unexpected error occurred"}
    }
    assert "private implementation detail" not in response.text


def test_request_validation_uses_stable_error_envelope() -> None:
    app = FastAPI()
    install_error_handlers(app)

    @app.get("/number")
    def number(value: int) -> dict[str, int]:
        return {"value": value}

    with TestClient(app) as client:
        response = client.get("/number", params={"value": "not-an-integer"})

    assert response.status_code == 422
    assert response.json() == {
        "error": {"code": "invalid_request", "message": "Request input is invalid"}
    }
