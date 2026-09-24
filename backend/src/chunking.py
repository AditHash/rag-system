"""Deterministic character-based chunking with page and offset metadata."""

from dataclasses import dataclass
from hashlib import sha256
from uuid import NAMESPACE_URL, UUID, uuid5

from src.extraction import ExtractedPage

DEFAULT_CHUNK_SIZE = 1_000
DEFAULT_CHUNK_OVERLAP = 150
MAX_CHUNK_SIZE = 10_000


@dataclass(frozen=True)
class DocumentChunk:
    """One piece of extracted text, retaining where it came from."""

    chunk_id: UUID
    document_id: UUID
    ordinal: int
    page_number: int | None
    start_offset: int
    end_offset: int
    content: str


def chunk_pages(
    pages: list[ExtractedPage],
    document_id: UUID,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[DocumentChunk]:
    """Split each extracted page into bounded, overlapping character windows."""
    _validate_settings(chunk_size, overlap)
    chunks: list[DocumentChunk] = []

    for page in pages:
        if page.start_offset < 0 or page.end_offset - page.start_offset != len(page.text):
            raise ValueError("page offsets must match the extracted text")
        if not page.text.strip():
            continue

        page_start = 0
        while page_start < len(page.text):
            page_end = min(page_start + chunk_size, len(page.text))
            content = page.text[page_start:page_end]
            ordinal = len(chunks)
            absolute_start = page.start_offset + page_start
            absolute_end = page.start_offset + page_end
            chunk_id = _stable_chunk_id(
                document_id,
                page.page_number,
                ordinal,
                absolute_start,
                absolute_end,
                content,
            )
            chunks.append(
                DocumentChunk(
                    chunk_id=chunk_id,
                    document_id=document_id,
                    ordinal=ordinal,
                    page_number=page.page_number,
                    start_offset=absolute_start,
                    end_offset=absolute_end,
                    content=content,
                )
            )
            if page_end == len(page.text):
                break
            page_start = page_end - overlap

    return chunks


def _validate_settings(chunk_size: int, overlap: int) -> None:
    if not 1 <= chunk_size <= MAX_CHUNK_SIZE:
        raise ValueError(f"chunk_size must be between 1 and {MAX_CHUNK_SIZE}")
    if not 0 <= overlap <= chunk_size // 2:
        raise ValueError("overlap must be between zero and half of chunk_size")


def _stable_chunk_id(
    document_id: UUID,
    page_number: int | None,
    ordinal: int,
    start_offset: int,
    end_offset: int,
    content: str,
) -> UUID:
    content_hash = sha256(content.encode("utf-8")).hexdigest()
    identity = f"{document_id}:{page_number}:{ordinal}:{start_offset}:{end_offset}:{content_hash}"
    return uuid5(NAMESPACE_URL, identity)
