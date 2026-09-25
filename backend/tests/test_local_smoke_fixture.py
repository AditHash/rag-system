"""The documented manual smoke fixture exercises local extraction and chunking."""

from pathlib import Path
from uuid import UUID

from src.chunking import chunk_pages
from src.extraction import extract_txt
from src.validation import validate_upload

SMOKE_FILE = Path(__file__).resolve().parents[2] / "docs/samples/local-smoke.txt"


def test_manual_smoke_fixture_passes_upload_extraction_and_chunking() -> None:
    content = SMOKE_FILE.read_bytes()
    validate_upload("local-smoke.txt", "text/plain", content)

    pages = extract_txt(content)
    chunks = chunk_pages(pages, UUID("00000000-0000-0000-0000-000000000001"))

    assert len(chunks) == 1
    assert chunks[0].page_number is None
    assert chunks[0].start_offset == 0
    assert chunks[0].end_offset == len(content.decode("utf-8"))
    assert "keeps uploaded records for 30 days" in chunks[0].content
