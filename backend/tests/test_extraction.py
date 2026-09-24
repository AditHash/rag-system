"""Page and text extraction tests using small in-memory PDF documents."""

import pytest

from src.extraction import DocumentExtractionError, extract_pdf_pages, extract_txt


def test_pdf_extraction_preserves_page_numbers_and_offsets() -> None:
    pages = extract_pdf_pages(_make_pdf(["First page", "", "Third page"]))
    assert [(page.page_number, page.text) for page in pages] == [
        (1, "First page"),
        (2, ""),
        (3, "Third page"),
    ]
    assert [(page.start_offset, page.end_offset) for page in pages] == [
        (0, len(page.text)) for page in pages
    ]


def test_invalid_and_textless_pdfs_have_clear_errors() -> None:
    with pytest.raises(DocumentExtractionError, match="invalid or unreadable"):
        extract_pdf_pages(b"not a PDF")
    with pytest.raises(DocumentExtractionError, match="no extractable text"):
        extract_pdf_pages(_make_pdf(["", "  "]))
    with pytest.raises(DocumentExtractionError, match="file is empty"):
        extract_pdf_pages(b"")


def test_txt_extraction_preserves_text_and_offsets() -> None:
    pages = extract_txt(b"  Exact text\nwith newlines.  ")
    assert len(pages) == 1
    assert pages[0].page_number is None
    assert pages[0].text == "  Exact text\nwith newlines.  "
    assert pages[0].start_offset == 0
    assert pages[0].end_offset == len(pages[0].text)


def test_invalid_or_blank_txt_is_rejected() -> None:
    with pytest.raises(DocumentExtractionError, match="must use UTF-8"):
        extract_txt(b"\xff")
    with pytest.raises(DocumentExtractionError, match="contains no text"):
        extract_txt(b" \n\t")


def _make_pdf(page_texts: list[str]) -> bytes:
    """Build a minimal, uncompressed PDF with Helvetica text on its pages."""
    page_ids = [3 + index * 2 for index in range(len(page_texts))]
    content_ids = [page_id + 1 for page_id in page_ids]
    font_id = 3 + len(page_texts) * 2
    objects: list[bytes] = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        (
            f"<< /Type /Pages /Kids [{' '.join(f'{item} 0 R' for item in page_ids)}] "
            f"/Count {len(page_ids)} >>"
        ).encode(),
    ]

    for content_id, text in zip(content_ids, page_texts, strict=True):
        escaped_text = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        stream = f"BT /F1 12 Tf 72 720 Td ({escaped_text}) Tj ET".encode("ascii")
        page = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 {font_id} 0 R >> >> /Contents {content_id} 0 R >>"
        ).encode()
        content = f"<< /Length {len(stream)} >>\nstream\n".encode() + stream + b"\nendstream"
        objects.extend([page, content])
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    pdf = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for object_id, body in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf.extend(f"{object_id} 0 obj\n".encode() + body + b"\nendobj\n")

    xref_offset = len(pdf)
    pdf.extend(f"xref\n0 {len(offsets)}\n".encode())
    pdf.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010} 00000 n \n".encode())
    pdf.extend(
        f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\n"
        f"startxref\n{xref_offset}\n%%EOF\n".encode()
    )
    return bytes(pdf)
