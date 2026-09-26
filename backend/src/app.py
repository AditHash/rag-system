"""FastAPI routes for ingestion, retrieval, and document Q&A."""

import re
from typing import Annotated, Literal

from fastapi import FastAPI, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from src import config
from src.generation import generate_answer
from src.ingest import ingest_file
from src.retrieval import search_documents

app = FastAPI(title="Document Q&A API", version="0.1.0")
REFUSAL = "I could not find enough information in the uploaded documents."


class SearchRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    top_k: int = Field(default=5, ge=1, le=10)


class ChatRequest(SearchRequest):
    thinking_mode: bool = False


class IngestResponse(BaseModel):
    document_id: str
    source: str
    status: Literal["indexed"]
    chunk_count: int = Field(ge=0)


class SearchResultResponse(BaseModel):
    text: str
    source: str
    page: int | None = None
    document_id: str | None = None
    chunk_index: int | None = None
    distance: float


class SearchResponse(BaseModel):
    question: str
    results: list[SearchResultResponse]


class CitedSourceResponse(SearchResultResponse):
    source_id: int


class ChatResponse(BaseModel):
    status: Literal["ANSWERED", "INSUFFICIENT_CONTEXT"]
    answer: str
    sources: list[CitedSourceResponse]


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/v1/ingest", response_model=IngestResponse)
async def ingest(file: Annotated[UploadFile, File()]) -> IngestResponse:
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

    return IngestResponse(
        document_id=document_id,
        source=filename,
        status="indexed",
        chunk_count=chunk_count,
    )


@app.post("/api/v1/search", response_model=SearchResponse)
def search(request: SearchRequest) -> SearchResponse:
    """Return nearest chunks so retrieval can be checked on its own."""
    if not request.question.strip():
        raise HTTPException(status_code=422, detail="Question cannot be blank.")
    try:
        results = search_documents(request.question, request.top_k)
    except Exception as error:
        raise HTTPException(
            status_code=503,
            detail="Search failed. Check database, AWS credentials, and Bedrock access.",
        ) from error

    return SearchResponse(question=request.question, results=results)


@app.post("/api/v1/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    """Retrieve source chunks and ask a Bedrock model to answer from them."""
    if not request.question.strip():
        raise HTTPException(status_code=422, detail="Question cannot be blank.")

    try:
        chunks = search_documents(request.question, request.top_k)
        if not chunks:
            return ChatResponse(
                status="INSUFFICIENT_CONTEXT", answer=REFUSAL, sources=[]
            )

        answer = generate_answer(
            request.question, chunks, thinking_mode=request.thinking_mode
        ).strip()
    except Exception as error:
        raise HTTPException(
            status_code=503,
            detail="Chat failed. Check database, AWS credentials, and Bedrock access.",
        ) from error

    if answer.casefold() == "insufficient_context":
        return ChatResponse(status="INSUFFICIENT_CONTEXT", answer=REFUSAL, sources=[])

    citations = [int(value) for value in re.findall(r"\[(\d+)\]", answer)]
    if not citations or any(value < 1 or value > len(chunks) for value in citations):
        return ChatResponse(status="INSUFFICIENT_CONTEXT", answer=REFUSAL, sources=[])

    source_ids = list(dict.fromkeys(citations))
    sources = [
        {"source_id": source_id, **chunks[source_id - 1]}
        for source_id in source_ids
    ]
    return ChatResponse(status="ANSWERED", answer=answer, sources=sources)
