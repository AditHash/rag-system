"""FastAPI routes for ingestion, retrieval, and document Q&A."""

import logging
import re
from contextlib import asynccontextmanager
from typing import Annotated, AsyncIterator, Literal
from uuid import UUID

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from src import config
from src.auth import (
    authenticate_user,
    bearer,
    create_token,
    create_user,
    create_users_table,
    current_user,
    revoke_token,
)
from src.generation import generate_answer
from src.ingest import ingest_file
from src.retrieval import rerank_documents, search_documents
@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    await run_in_threadpool(create_users_table)
    yield


app = FastAPI(title="Document Q&A API", version="0.1.0", lifespan=lifespan)
REFUSAL = "I could not find enough information in the uploaded documents."
logger = logging.getLogger(__name__)


class AuthRequest(BaseModel):
    username: str = Field(min_length=3, max_length=32, pattern=r"^[A-Za-z0-9_]+$")
    password: str = Field(min_length=8, max_length=128)


class UserResponse(BaseModel):
    id: str
    username: str


class AuthResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    user: UserResponse


class SearchRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    top_k: int = Field(default=5, ge=1, le=10)
    document_id: UUID | None = None


class ChatRequest(SearchRequest):
    top_k: int = Field(default=5, ge=1, le=5)
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
    rerank_score: float


class ChatResponse(BaseModel):
    status: Literal["ANSWERED", "INSUFFICIENT_CONTEXT", "UNVERIFIED_ANSWER"]
    answer: str
    sources: list[CitedSourceResponse]


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/v1/signup", response_model=AuthResponse, status_code=201)
def signup(request: AuthRequest) -> AuthResponse:
    user = create_user(request.username, request.password)
    return AuthResponse(access_token=create_token(user["id"]), user=UserResponse(**user))


@app.post("/api/v1/login", response_model=AuthResponse)
def login(request: AuthRequest) -> AuthResponse:
    user = authenticate_user(request.username, request.password)
    return AuthResponse(access_token=create_token(user["id"]), user=UserResponse(**user))


@app.get("/api/v1/me", response_model=UserResponse)
def me(user: Annotated[dict[str, str], Depends(current_user)]) -> UserResponse:
    return UserResponse(**user)


@app.post("/api/v1/logout", status_code=204)
def logout(
    user: Annotated[dict[str, str], Depends(current_user)],
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> None:
    revoke_token(credentials)


@app.post("/api/v1/ingest", response_model=IngestResponse)
async def ingest(
    file: Annotated[UploadFile, File()],
    user: Annotated[dict[str, str], Depends(current_user)],
) -> IngestResponse:
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
            ingest_file, filename, content, user["id"]
        )
    except (UnicodeError, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except Exception as error:
        logger.exception("Document ingestion failed")
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
def search(
    request: SearchRequest,
    user: Annotated[dict[str, str], Depends(current_user)],
) -> SearchResponse:
    """Return nearest chunks so retrieval can be checked on its own."""
    if not request.question.strip():
        raise HTTPException(status_code=422, detail="Question cannot be blank.")
    try:
        results = search_documents(
            request.question,
            request.top_k,
            user["id"],
            str(request.document_id) if request.document_id else None,
        )
    except Exception as error:
        raise HTTPException(
            status_code=503,
            detail="Search failed. Check database, AWS credentials, and Bedrock access.",
        ) from error

    return SearchResponse(question=request.question, results=results)


@app.post("/api/v1/chat", response_model=ChatResponse)
def chat(
    request: ChatRequest,
    user: Annotated[dict[str, str], Depends(current_user)],
) -> ChatResponse:
    """Retrieve source chunks and ask a Bedrock model to answer from them."""
    if not request.question.strip():
        raise HTTPException(status_code=422, detail="Question cannot be blank.")

    try:
        chunks = rerank_documents(
            request.question,
            search_documents(
                request.question,
                request.top_k,
                user["id"],
                str(request.document_id) if request.document_id else None,
            ),
        )
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
        logger.info("Chat answer had no valid source citations")
        return ChatResponse(
            status="UNVERIFIED_ANSWER",
            answer=(
                "The model did not return a verifiable cited answer. "
                "Try normal mode or rephrase the question."
            ),
            sources=[],
        )

    source_ids = list(dict.fromkeys(citations))
    sources = [
        {"source_id": source_id, **chunks[source_id - 1]}
        for source_id in source_ids
    ]
    return ChatResponse(status="ANSWERED", answer=answer, sources=sources)
