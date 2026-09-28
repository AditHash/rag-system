"""Run the paper question set against a live Document Q&A API."""

import json
import os
import secrets
import string
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
QUESTIONS = ROOT / "eval/questions_llm_agents.jsonl"
PDF = ROOT / ("sample-pdfs/LLM Agents Can Easily Tamper With Their Own Traces - 2609.30266v1.pdf")
BASE_URL = os.environ.get("RAG_API_URL", "https://rag-demo.cwmgenai.com").rstrip("/")


def load_questions() -> list[dict]:
    return [json.loads(line) for line in QUESTIONS.read_text().splitlines() if line]


def score(question: dict, result: dict) -> dict:
    answer = result["answer"].casefold()
    sources = result.get("sources", [])
    if not question["answerable"]:
        passed = result["status"] == "INSUFFICIENT_CONTEXT" and not sources
        return {"pass": passed, "fact_groups": None, "source_page": None}

    groups = question["expected_terms"]
    matched = sum(any(term.casefold() in answer for term in group.split("|")) for group in groups)
    source_page = any(
        source.get("source") in question["sources"]
        and source.get("page") in question["expected_pages"]
        for source in sources
    )
    passed = result["status"] == "ANSWERED" and matched == len(groups) and source_page
    return {
        "pass": passed,
        "fact_groups": f"{matched}/{len(groups)}",
        "source_page": source_page,
    }


def main() -> None:
    if not PDF.is_file():
        raise SystemExit(f"Evaluation PDF not found: {PDF}")

    username = "eval_" + secrets.token_hex(6)
    alphabet = string.ascii_letters + string.digits
    password = "E" + "".join(secrets.choice(alphabet) for _ in range(30)) + "9!"
    timeout_seconds = int(os.environ.get("RAG_EVAL_TIMEOUT_SECONDS", "900"))
    client = httpx.Client(base_url=BASE_URL, timeout=timeout_seconds)
    token = None
    document_id = None
    results = []
    started = time.monotonic()
    try:
        response = client.post("/api/v1/signup", json={"username": username, "password": password})
        response.raise_for_status()
        token = response.json()["access_token"]
        client.headers["Authorization"] = f"Bearer {token}"

        with PDF.open("rb") as pdf:
            response = client.post(
                "/api/v1/ingest",
                files={"file": (PDF.name, pdf, "application/pdf")},
            )
        response.raise_for_status()
        indexed = response.json()
        document_id = indexed["document_id"]

        for question in load_questions():
            response = client.post(
                "/api/v1/chat",
                json={
                    "question": question["question"],
                    "top_k": 5,
                    "document_id": document_id,
                    "thinking_mode": False,
                },
            )
            response.raise_for_status()
            output = response.json()
            results.append(
                {
                    "id": question["id"],
                    **score(question, output),
                    "status": output["status"],
                    "source_pages": [item.get("page") for item in output.get("sources", [])],
                    "rerank_scores": [
                        item.get("rerank_score") for item in output.get("sources", [])
                    ],
                }
            )
            mark = "PASS" if results[-1]["pass"] else "FAIL"
            print(f"{question['id']}: {results[-1]['status']} ({mark})", flush=True)

        question_set = load_questions()
        output = {
            "api": BASE_URL,
            "chunk_size": int(os.environ.get("CHUNK_SIZE", "0")),
            "chunk_overlap": int(os.environ.get("CHUNK_OVERLAP", "0")),
            "document_id": document_id,
            "chunk_count": indexed["chunk_count"],
            "question_count": len(results),
            "passed": sum(item["pass"] for item in results),
            "answerable_passed": sum(
                item["pass"]
                for item, question in zip(results, question_set, strict=True)
                if question["answerable"]
            ),
            "refusals_passed": sum(
                item["pass"]
                for item, question in zip(results, question_set, strict=True)
                if not question["answerable"]
            ),
            "elapsed_seconds": round(time.monotonic() - started, 1),
            "questions": results,
        }
        result_path = Path(os.environ.get("RESULT_PATH", "/tmp/rag-eval-result.json"))
        result_path.write_text(json.dumps(output, indent=2) + "\n")
        print(json.dumps(output, indent=2))
        print(f"Detailed result saved to {result_path}")
    finally:
        if token:
            if document_id:
                client.delete(f"/api/v1/documents/{document_id}")
            client.post("/api/v1/logout")
        client.close()


if __name__ == "__main__":
    try:
        main()
    except httpx.HTTPStatusError as error:
        print(
            f"API request failed with HTTP {error.response.status_code}: {error.response.text}",
            file=sys.stderr,
        )
        raise SystemExit(1) from error
