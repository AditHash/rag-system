"""Small validators for chat questions and uploaded document content."""

from pathlib import Path

from fastapi import HTTPException

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_QUESTION_CHARACTERS = 4_000


def validate_question(question: str) -> str:
    """Trim a question and reject empty or excessively long input."""
    normalized = question.strip()
    if not normalized:
        raise HTTPException(status_code=422, detail="Question must not be empty")
    if len(normalized) > MAX_QUESTION_CHARACTERS:
        raise HTTPException(status_code=422, detail="Question is too long")
    return normalized


def validate_upload(filename: str, content_type: str, data: bytes) -> None:
    """Accept a bounded PDF or UTF-8 plain-text file with a matching signature."""
    if not data:
        raise HTTPException(status_code=422, detail="File must not be empty")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File exceeds the 10 MiB limit")

    suffix = Path(filename).suffix.lower()
    if suffix == ".pdf" and content_type == "application/pdf":
        if not data.startswith(b"%PDF-"):
            raise HTTPException(status_code=422, detail="File is not a valid PDF")
        return

    if suffix == ".txt" and content_type == "text/plain":
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError as error:
            raise HTTPException(status_code=422, detail="Text file must use UTF-8") from error
        if not text.strip():
            raise HTTPException(status_code=422, detail="Text file must not be blank")
        return

    raise HTTPException(status_code=415, detail="Only PDF and UTF-8 TXT files are supported")
