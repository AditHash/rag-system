CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE ingestion_jobs (
    id UUID PRIMARY KEY,
    owner_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'PENDING'
        CHECK (status IN ('PENDING', 'PROCESSING', 'COMPLETED', 'FAILED')),
    stage TEXT NOT NULL DEFAULT 'PENDING',
    completed_documents INTEGER NOT NULL DEFAULT 0 CHECK (completed_documents >= 0),
    total_documents INTEGER NOT NULL DEFAULT 0 CHECK (total_documents >= completed_documents),
    sanitized_error TEXT,
    idempotency_key TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (id, owner_id),
    UNIQUE (owner_id, idempotency_key)
);

CREATE INDEX ingestion_jobs_owner_created_idx
    ON ingestion_jobs (owner_id, created_at DESC);

CREATE TABLE documents (
    id UUID PRIMARY KEY,
    ingestion_id UUID NOT NULL,
    owner_id TEXT NOT NULL,
    original_filename TEXT NOT NULL,
    s3_key TEXT NOT NULL UNIQUE,
    checksum_sha256 CHAR(64) NOT NULL
        CHECK (checksum_sha256 ~ '^[0-9a-f]{64}$'),
    content_type TEXT NOT NULL,
    byte_size BIGINT NOT NULL CHECK (byte_size > 0),
    status TEXT NOT NULL DEFAULT 'PROCESSING'
        CHECK (status IN ('PROCESSING', 'READY', 'FAILED')),
    embedding_model TEXT NOT NULL,
    embedding_dimension SMALLINT NOT NULL DEFAULT 1024
        CHECK (embedding_dimension = 1024),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    FOREIGN KEY (ingestion_id, owner_id)
        REFERENCES ingestion_jobs (id, owner_id) ON DELETE CASCADE
);

CREATE INDEX documents_owner_status_idx ON documents (owner_id, status);
CREATE INDEX documents_ingestion_idx ON documents (ingestion_id);

CREATE TABLE chunks (
    id UUID PRIMARY KEY,
    document_id UUID NOT NULL REFERENCES documents (id) ON DELETE CASCADE,
    ordinal INTEGER NOT NULL CHECK (ordinal >= 0),
    page_number INTEGER CHECK (page_number IS NULL OR page_number > 0),
    start_offset INTEGER CHECK (start_offset IS NULL OR start_offset >= 0),
    end_offset INTEGER CHECK (end_offset IS NULL OR end_offset >= 0),
    content TEXT NOT NULL CHECK (length(btrim(content)) > 0),
    embedding VECTOR(1024) NOT NULL,
    chunker_version TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (document_id, ordinal),
    CHECK (
        start_offset IS NULL OR end_offset IS NULL OR end_offset > start_offset
    )
);

CREATE INDEX chunks_document_ordinal_idx ON chunks (document_id, ordinal);
CREATE INDEX chunks_embedding_cosine_idx
    ON chunks USING hnsw (embedding vector_cosine_ops);

CREATE VIEW ready_chunks AS
SELECT
    chunks.id AS chunk_id,
    chunks.document_id,
    documents.owner_id,
    chunks.ordinal,
    chunks.page_number,
    chunks.start_offset,
    chunks.end_offset,
    chunks.content,
    chunks.embedding,
    documents.original_filename
FROM chunks
JOIN documents ON documents.id = chunks.document_id
WHERE documents.status = 'READY';
