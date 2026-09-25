"""Read PDF/TXT uploads and store LangChain chunks in PostgreSQL."""

from io import BytesIO
from uuid import uuid4

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pypdf import PdfReader
from pypdf.errors import PdfReadError

from src import config
from src.retrieval import get_vector_store


def read_upload(filename: str, content: bytes) -> list[Document]:
    """Return one LangChain document per page, with source information."""
    if filename.lower().endswith(".txt"):
        text = content.decode("utf-8").strip()
        pages = [Document(page_content=text, metadata={"page": 1})]
    elif filename.lower().endswith(".pdf"):
        try:
            reader = PdfReader(BytesIO(content))
        except PdfReadError as error:
            raise ValueError("The PDF could not be read.") from error
        pages = [
            Document(
                page_content=(page.extract_text() or "").strip(),
                metadata={"page": page_number},
            )
            for page_number, page in enumerate(reader.pages, start=1)
        ]
    else:
        raise ValueError("Only PDF and TXT files are supported.")

    pages = [page for page in pages if page.page_content]
    if not pages:
        raise ValueError("No readable text was found in the file.")

    document_id = str(uuid4())
    for page in pages:
        page.metadata.update({"document_id": document_id, "source": filename})
    return pages


def ingest_file(filename: str, content: bytes) -> tuple[str, int]:
    """Split a file, embed its chunks, and add them to PostgreSQL."""
    pages = read_upload(filename, content)
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=config.CHUNK_SIZE,
        chunk_overlap=config.CHUNK_OVERLAP,
        add_start_index=True,
    )
    chunks = splitter.split_documents(pages)
    for chunk_index, chunk in enumerate(chunks):
        chunk.metadata["chunk_index"] = chunk_index

    document_id = pages[0].metadata["document_id"]
    chunk_ids = [str(uuid4()) for _ in chunks]
    get_vector_store().add_documents(chunks, ids=chunk_ids)
    return document_id, len(chunks)
