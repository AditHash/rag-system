"""Read PDF/TXT uploads and store LangChain chunks in PostgreSQL."""

from io import BytesIO
import logging
from uuid import uuid4

import boto3
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pypdf import PdfReader
from pypdf.errors import PdfReadError

from src import config
from src.documents import save_document
from src.retrieval import get_vector_store

logger = logging.getLogger(__name__)


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


def ingest_file(filename: str, content: bytes, user_id: str) -> tuple[str, int]:
    """Save the original if configured, then embed its chunks in PostgreSQL."""
    pages = read_upload(filename, content)
    document_id = pages[0].metadata["document_id"]
    s3_key = None
    if config.S3_BUCKET:
        extension = filename.rsplit(".", 1)[-1].lower()
        s3_key = f"users/{user_id}/documents/{document_id}/original.{extension}"
        boto3.client("s3", region_name=config.AWS_REGION).put_object(
            Bucket=config.S3_BUCKET,
            Key=s3_key,
            Body=content,
            ContentType="application/pdf" if extension == "pdf" else "text/plain",
            ServerSideEncryption="AES256",
        )

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=config.CHUNK_SIZE,
        chunk_overlap=config.CHUNK_OVERLAP,
        add_start_index=True,
    )
    chunks = splitter.split_documents(pages)
    for chunk_index, chunk in enumerate(chunks):
        chunk.metadata["chunk_index"] = chunk_index
        chunk.metadata["user_id"] = user_id

    chunk_ids = [str(uuid4()) for _ in chunks]
    try:
        get_vector_store().add_documents(chunks, ids=chunk_ids)
        save_document(document_id, user_id, filename, s3_key, len(chunks))
    except Exception:
        try:
            get_vector_store().delete(ids=chunk_ids)
        except Exception:
            logger.exception("Could not remove chunks after failed ingestion")
        if s3_key:
            try:
                boto3.client("s3", region_name=config.AWS_REGION).delete_object(
                    Bucket=config.S3_BUCKET, Key=s3_key
                )
            except Exception:
                logger.exception("Could not remove S3 object after failed ingestion")
        raise
    return document_id, len(chunks)
