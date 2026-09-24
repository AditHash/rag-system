"""S3 adapter tests use a fake client and make no AWS requests."""

from io import BytesIO
from uuid import uuid4

import pytest

from src.storage import S3DocumentStore


class FakeS3Client:
    def __init__(self) -> None:
        self.put_call: dict[str, object] | None = None
        self.get_call: dict[str, object] | None = None
        self.content: bytes = b""
        self.error: Exception | None = None

    def put_object(self, **kwargs: object) -> None:
        if self.error:
            raise self.error
        self.put_call = kwargs

    def get_object(self, **kwargs: object) -> dict[str, BytesIO]:
        if self.error:
            raise self.error
        self.get_call = kwargs
        return {"Body": BytesIO(self.content)}


def test_put_and_get_use_owner_scoped_key_and_private_defaults() -> None:
    client = FakeS3Client()
    store = S3DocumentStore(bucket="private-documents", client=client)
    document_id = uuid4()
    data = b"%PDF-1.7 sample"

    key = store.put_document("demo-user", document_id, data, "application/pdf")
    client.content = data
    retrieved = store.get_document("demo-user", document_id)

    assert key == f"documents/demo-user/{document_id}"
    assert client.put_call == {
        "Bucket": "private-documents",
        "Key": key,
        "Body": data,
        "ContentType": "application/pdf",
        "ServerSideEncryption": "AES256",
    }
    assert "ACL" not in client.put_call
    assert client.get_call == {"Bucket": "private-documents", "Key": key}
    assert retrieved == data


def test_store_requires_bucket_without_creating_aws_client(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("S3_BUCKET", raising=False)
    with pytest.raises(ValueError, match="S3_BUCKET is required"):
        S3DocumentStore()


def test_store_rejects_invalid_owner_empty_body_and_unsupported_type() -> None:
    store = S3DocumentStore(bucket="private-documents", client=FakeS3Client())
    document_id = uuid4()

    with pytest.raises(ValueError, match="owner_id"):
        store.put_document("../other", document_id, b"content", "text/plain")
    with pytest.raises(ValueError, match="must not be empty"):
        store.put_document("demo-user", document_id, b"", "text/plain")
    with pytest.raises(ValueError, match="only PDF"):
        store.put_document("demo-user", document_id, b"data", "image/png")


def test_s3_client_errors_are_propagated() -> None:
    client = FakeS3Client()
    client.error = RuntimeError("s3 unavailable")
    store = S3DocumentStore(bucket="private-documents", client=client)

    with pytest.raises(RuntimeError, match="s3 unavailable"):
        store.put_document("demo-user", uuid4(), b"content", "text/plain")
    with pytest.raises(RuntimeError, match="s3 unavailable"):
        store.get_document("demo-user", uuid4())
