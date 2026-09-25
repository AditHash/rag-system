"""Small FastAPI API for document ingestion and similarity search."""

import secrets
from typing import Annotated

from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from src import config
from src.ingest import ingest_file
from src.retrieval import search_documents

app = FastAPI(title="Document Search API", version="0.1.0")


def check_api_key(api_key: str | None = Header(default=None, alias="X-API-Key")) -> None:
    """Protect the demo routes with the key configured in the environment."""
    if not config.API_KEY:
        raise HTTPException(status_code=503, detail="API_KEY is not configured.")
    if api_key is None or not secrets.compare_digest(api_key, config.API_KEY):
        raise HTTPException(status_code=401, detail="Invalid API key.")


class SearchRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    top_k: int = Field(default=5, ge=1, le=10)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/v1/ingest", dependencies=[Depends(check_api_key)])
async def ingest(file: Annotated[UploadFile, File()]) -> dict[str, object]:
    """Extract, split, embed, and store one PDF or TXT document."""
    filename = file.filename or ""
    if not filename.lower().endswith((".pdf", ".txt")):
        raise HTTPException(status_code=415, detail="Upload a PDF or TXT file.")

    content = await file.read(config.MAX_UPLOAD_BYTES + 1)
    if not content:
        raise HTTPException(status_code=400, detail="The uploaded file is empty.")
    if len(content) > config.MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File exceeds the 10 MiB limit.")

    try:
        document_id, chunk_count = await run_in_threadpool(
            ingest_file, filename, content
        )
    except (UnicodeError, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(
            status_code=503,
            detail="Ingestion failed. Check database, AWS credentials, and Bedrock access.",
        ) from error

    return {
        "document_id": document_id,
        "source": filename,
        "status": "indexed",
        "chunk_count": chunk_count,
    }


@app.post("/api/v1/search", dependencies=[Depends(check_api_key)])
def search(request: SearchRequest) -> dict[str, object]:
    """Return the nearest stored chunks for the question."""
    if not request.question.strip():
        raise HTTPException(status_code=422, detail="Question cannot be blank.")
    try:
        results = search_documents(request.question, request.top_k)
    except Exception as error:
        raise HTTPException(
            status_code=503,
            detail="Search failed. Check database, AWS credentials, and Bedrock access.",
        ) from error

    return {"question": request.question, "results": results}
