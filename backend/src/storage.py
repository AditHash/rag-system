"""Private S3 storage for original document bytes."""

import os
import re
from typing import Any
from uuid import UUID

import boto3

from src.config import AWS_REGION

_OWNER_ID_PATTERN = re.compile(r"[A-Za-z0-9_-]{1,128}\Z")
_ALLOWED_CONTENT_TYPES = {"application/pdf", "text/plain"}


class S3DocumentStore:
    """Store and retrieve document bytes using deterministic, scoped keys."""

    def __init__(self, bucket: str | None = None, client: Any | None = None) -> None:
        self.bucket = bucket or os.getenv("S3_BUCKET")
        if not self.bucket:
            raise ValueError("S3_BUCKET is required")
        self.client = client if client is not None else boto3.client("s3", region_name=AWS_REGION)

    def put_document(
        self,
        owner_id: str,
        document_id: UUID,
        data: bytes,
        content_type: str,
    ) -> str:
        """Upload bytes and return the key to persist alongside document metadata."""
        if not _OWNER_ID_PATTERN.fullmatch(owner_id):
            raise ValueError("owner_id must contain only letters, numbers, hyphens, or underscores")
        if not data:
            raise ValueError("document data must not be empty")
        if content_type not in _ALLOWED_CONTENT_TYPES:
            raise ValueError("only PDF and plain-text documents are supported")

        key = self.key_for_document(owner_id, document_id)
        self.client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=data,
            ContentType=content_type,
            ServerSideEncryption="AES256",
        )
        return key

    def get_document(self, owner_id: str, document_id: UUID) -> bytes:
        """Download bytes from the owner/document key."""
        if not _OWNER_ID_PATTERN.fullmatch(owner_id):
            raise ValueError("owner_id must contain only letters, numbers, hyphens, or underscores")

        response = self.client.get_object(
            Bucket=self.bucket,
            Key=self.key_for_document(owner_id, document_id),
        )
        body = response["Body"]
        try:
            return body.read()
        finally:
            close = getattr(body, "close", None)
            if close is not None:
                close()

    @staticmethod
    def key_for_document(owner_id: str, document_id: UUID) -> str:
        """Return the deterministic key for a validated owner and document ID."""
        if not _OWNER_ID_PATTERN.fullmatch(owner_id):
            raise ValueError("owner_id must contain only letters, numbers, hyphens, or underscores")
        return f"documents/{owner_id}/{document_id}"
