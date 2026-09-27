"""Small, opt-in live API check and document Q&A evaluation."""

import json
import os
import re
import secrets
from io import BytesIO
from pathlib import Path
from uuid import UUID

import boto3
import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader, PdfWriter
from sqlalchemy import text

from src import config
from src.app import app
from src.auth import get_engine

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "eval" / "fixtures"
QUESTIONS = ROOT / "eval" / "questions_v1.jsonl"


def load_cases() -> list[dict]:
    return [json.loads(line) for line in QUESTIONS.read_text().splitlines() if line.strip()]


def test_evaluation_cases_have_known_evidence() -> None:
    cases = load_cases()
    assert 10 <= len(cases) <= 15
    assert len({case["id"] for case in cases}) == len(cases)
    assert any(not case["answerable"] for case in cases)
    for case in cases:
        assert case["question"].strip()
        assert case["expected_answer"].strip()
        assert case["answerable"] == bool(case["expected_terms"])
        assert case["answerable"] == bool(case["sources"])
        evidence = " ".join((FIXTURES / name).read_text() for name in case["sources"])
        for choices in case["expected_terms"]:
            assert any(choice.casefold() in evidence.casefold() for choice in choices.split("|"))


def score_case(case: dict, response: dict) -> dict:
    answer = re.sub(r"\[\d+\]", "", response["answer"]).casefold()
    actual_sources = {source["source"] for source in response["sources"]}
    if case["answerable"]:
        facts_found = all(
            any(choice.casefold() in answer for choice in choices.split("|"))
            for choices in case["expected_terms"]
        )
        sources_found = set(case["sources"]).issubset(actual_sources)
        passed = response["status"] == "ANSWERED" and facts_found and sources_found
    else:
        facts_found = None
        sources_found = None
        passed = response["status"] == "INSUFFICIENT_CONTEXT" and not actual_sources
    return {
        "id": case["id"],
        "question": case["question"],
        "expected_answerable": case["answerable"],
        "status": response["status"],
        "answer": response["answer"],
        "sources": sorted(actual_sources),
        "facts_found": facts_found,
        "sources_found": sources_found,
        "passed": passed,
    }


def cleanup(users: list[dict]) -> None:
    """Remove only the temporary users and documents created by this check."""
    if config.S3_BUCKET:
        s3 = boto3.client("s3", region_name=config.AWS_REGION)
        for user in users:
            prefix = f"users/{user['id']}/"
            response = s3.list_objects_v2(Bucket=config.S3_BUCKET, Prefix=prefix)
            for item in response.get("Contents", []):
                s3.delete_object(Bucket=config.S3_BUCKET, Key=item["Key"])

    with get_engine().begin() as connection:
        embeddings_exist = connection.execute(
            text("SELECT to_regclass('langchain_pg_embedding')")
        ).scalar()
        for user in users:
            if embeddings_exist:
                connection.execute(
                    text("DELETE FROM langchain_pg_embedding WHERE cmetadata->>'user_id' = :id"),
                    {"id": user["id"]},
                )
            connection.execute(
                text("DELETE FROM app_users WHERE id = :id"),
                {"id": UUID(user["id"])},
            )


@pytest.mark.skipif(os.getenv("RUN_LIVE") != "1", reason="Set RUN_LIVE=1 for billable API calls")
def test_live_api_and_evaluation() -> None:
    assert config.S3_BUCKET, "Set S3_BUCKET to check the S3 upload path."
    users = []
    with TestClient(app) as client:
        try:
            assert client.get("/health").status_code == 200
            assert client.get("/api/v1/me").status_code == 401

            password = secrets.token_urlsafe(16)
            tokens = []
            for _ in range(2):
                username = f"eval_{secrets.token_hex(5)}"
                response = client.post(
                    "/api/v1/signup", json={"username": username, "password": password}
                )
                assert response.status_code == 201, response.status_code
                body = response.json()
                users.append(body["user"])
                tokens.append(body["access_token"])

            alice = {"Authorization": f"Bearer {tokens[0]}"}
            bob = {"Authorization": f"Bearer {tokens[1]}"}
            assert client.get("/api/v1/me", headers=alice).json()["id"] == users[0]["id"]
            assert client.post(
                "/api/v1/ingest",
                files={"file": ("unauthorized.txt", b"hello", "text/plain")},
            ).status_code == 401
            assert client.post(
                "/api/v1/ingest",
                headers=alice,
                files={"file": ("bad.exe", b"hello", "application/octet-stream")},
            ).status_code == 415
            assert client.post(
                "/api/v1/search", headers=alice, json={"question": "   "}
            ).status_code == 422
            login = client.post(
                "/api/v1/login",
                json={"username": users[0]["username"], "password": password},
            )
            assert login.status_code == 200
            assert client.post(
                "/api/v1/login",
                json={"username": users[0]["username"], "password": "wrong-pass"},
            ).status_code == 401

            for name in ("operations.txt", "travel.txt"):
                content = (FIXTURES / name).read_bytes()
                response = client.post(
                    "/api/v1/ingest",
                    headers=alice,
                    files={"file": (name, content, "text/plain")},
                )
                assert response.status_code == 200, response.status_code
                assert response.json()["chunk_count"] > 0
                s3_key = (
                    f"users/{users[0]['id']}/documents/"
                    f"{response.json()['document_id']}/original.txt"
                )
                stored = boto3.client("s3", region_name=config.AWS_REGION).head_object(
                    Bucket=config.S3_BUCKET, Key=s3_key
                )
                assert stored["ServerSideEncryption"] == "AES256"

            private = client.post(
                "/api/v1/ingest",
                headers=bob,
                files={"file": ("private.txt", b"The private code is marigold.\n", "text/plain")},
            )
            assert private.status_code == 200, private.status_code
            private_id = private.json()["document_id"]

            samples = sorted((ROOT / "sample-pdfs").glob("*.pdf"))
            if samples:
                writer = PdfWriter()
                writer.add_page(PdfReader(samples[0]).pages[0])
                pdf = BytesIO()
                writer.write(pdf)
                uploaded = client.post(
                    "/api/v1/ingest",
                    headers=bob,
                    files={"file": ("sample-page.pdf", pdf.getvalue(), "application/pdf")},
                )
                assert uploaded.status_code == 200, uploaded.status_code
                pdf_results = client.post(
                    "/api/v1/search",
                    headers=bob,
                    json={
                        "question": "What is this research paper about?",
                        "document_id": uploaded.json()["document_id"],
                    },
                )
                assert pdf_results.status_code == 200
                assert pdf_results.json()["results"][0]["page"] == 1

            search = client.post(
                "/api/v1/search", headers=alice,
                json={"question": "How long are application logs retained?"},
            )
            assert search.status_code == 200
            assert search.json()["results"][0]["source"] == "operations.txt"
            assert all(item["source"] != "private.txt" for item in search.json()["results"])

            isolation = client.post(
                "/api/v1/search", headers=alice,
                json={"question": "What is the private code?", "document_id": private_id},
            )
            assert isolation.status_code == 200
            assert isolation.json()["results"] == []
            isolated_chat = client.post(
                "/api/v1/chat", headers=alice,
                json={"question": "What is the private code?", "document_id": private_id},
            )
            assert isolated_chat.status_code == 200
            assert isolated_chat.json()["status"] == "INSUFFICIENT_CONTEXT"

            cases = load_cases()
            if os.getenv("EVAL_SMOKE") == "1":
                cases = [case for case in cases if case["id"] in {"q01", "q10"}]
            scores = []
            for case in cases:
                response = client.post(
                    "/api/v1/chat", headers=alice,
                    json={"question": case["question"], "top_k": 5, "thinking_mode": False},
                )
                assert response.status_code == 200, (case["id"], response.status_code)
                scores.append(score_case(case, response.json()))

            summary = {
                "total": len(scores),
                "passed": sum(item["passed"] for item in scores),
                "answerable_passed": sum(
                    item["passed"] for item in scores if item["expected_answerable"]
                ),
                "refusals_passed": sum(
                    item["passed"] for item in scores if not item["expected_answerable"]
                ),
                "cases": scores,
            }
            result_name = (
                "results_smoke.json" if os.getenv("EVAL_SMOKE") == "1" else "results_v1.json"
            )
            (ROOT / "eval" / result_name).write_text(json.dumps(summary, indent=2) + "\n")
            print(f"Evaluation: {summary['passed']}/{summary['total']} passed")
            print("Failed cases:", [item["id"] for item in scores if not item["passed"]])

            assert client.post("/api/v1/logout", headers=alice).status_code == 204
            assert client.get("/api/v1/me", headers=alice).status_code == 401
        finally:
            cleanup(users)
