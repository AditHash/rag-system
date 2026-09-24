"""Text extraction that retains source page and character-offset metadata."""

from dataclasses import dataclass
from io import BytesIO

from pypdf import PdfReader
from pypdf.errors import PdfReadError


@dataclass(frozen=True)
class ExtractedPage:
    """Text from one PDF page or the whole text file with offsets in that text."""

    page_number: int | None
    text: str
    start_offset: int
    end_offset: int


class DocumentExtractionError(ValueError):
    """The source file is invalid, unsupported, or contains no usable text."""


def extract_pdf_pages(data: bytes) -> list[ExtractedPage]:
    """Extract each PDF page separately; blank pages keep their page positions."""
    if not data:
        raise DocumentExtractionError("PDF file is empty")

    try:
        reader = PdfReader(BytesIO(data), strict=True)
    except (PdfReadError, OSError, ValueError):
        raise DocumentExtractionError("PDF file is invalid or unreadable") from None

    if reader.is_encrypted:
        raise DocumentExtractionError("Password-protected PDFs are not supported")
    if not reader.pages:
        raise DocumentExtractionError("PDF contains no pages")

    extracted_pages: list[ExtractedPage] = []
    for page_number, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
        except (PdfReadError, OSError, ValueError):
            raise DocumentExtractionError("PDF page text could not be extracted") from None
        extracted_pages.append(
            ExtractedPage(
                page_number=page_number,
                text=text,
                start_offset=0,
                end_offset=len(text),
            )
        )

    if not any(page.text.strip() for page in extracted_pages):
        raise DocumentExtractionError(
            "PDF contains no extractable text; scanned PDFs are unsupported"
        )
    return extracted_pages


def extract_txt(data: bytes) -> list[ExtractedPage]:
    """Decode one UTF-8 text file and preserve its characters and offsets."""
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        raise DocumentExtractionError("Text file must use UTF-8") from None
    if not text.strip():
        raise DocumentExtractionError("Text file contains no text")
    return [ExtractedPage(page_number=None, text=text, start_offset=0, end_offset=len(text))]
