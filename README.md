# Document Q&A backend

A small FastAPI backend for the first two RAG steps: ingest documents into a
vector store, then find relevant chunks for a question. It uses LangChain for
document chunks, Bedrock embeddings, and PostgreSQL/pgvector storage and search.

This version does not generate answers, rerank results, or refuse unsupported
questions. It returns retrieved passages and their source metadata so the
retrieval flow can be inspected before answer generation is added.

## Requirements

- Python 3.12 and `uv`
- PostgreSQL with the `vector` extension installed
- AWS credentials permitted to invoke the configured Bedrock embedding model
- A database user that can connect to the database and use the `vector` extension

No AWS resources are provisioned by these instructions. Embedding requests are
billable Bedrock calls.

## Configure and run

From `backend/`, copy `.env.example` to `.env`, fill in the local database URL
and a private API key, then export the settings into your shell. Use your normal
AWS credential chain (for example, `AWS_PROFILE`) for Bedrock access.

```bash
cd backend
cp .env.example .env
# Edit .env; do not commit it.
set -a
source .env
set +a
uv sync --frozen
uv run main.py
```

The database URL uses the psycopg 3 SQLAlchemy scheme, for example:

```text
postgresql+psycopg://user:password@localhost:5432/document_db
```

The LangChain vector store creates its own tables in the configured database.
The PostgreSQL server must already have pgvector installed. Model ID, region,
chunk size, overlap, collection name, database URL, and API key are configurable
in `backend/src/config.py` through environment variables. `AWS_PROFILE` is read
by the standard AWS credential chain and does not need to be copied into code.

Check the process health and interactive API documentation:

```bash
curl http://127.0.0.1:8000/health
# {"status":"ok"}
```

Open `http://127.0.0.1:8000/docs` to explore the two endpoints.

## Ingest a document

PDF and UTF-8 TXT files up to 10 MiB are accepted. The endpoint extracts text,
keeps the source filename and 1-based page in LangChain document metadata,
splits text into 1,000-character chunks with 150 characters of overlap by
default, embeds the chunks, and stores them in PostgreSQL.

```bash
curl --fail --show-error \
  -H "X-API-Key: $API_KEY" \
  -F 'file=@./example.pdf' \
  http://127.0.0.1:8000/api/v1/ingest
```

Example response:

```json
{
  "document_id": "2e7a...",
  "source": "example.pdf",
  "status": "indexed",
  "chunk_count": 8
}
```

Ingestion is synchronous in this demo. It returns only after the Bedrock
embeddings and PostgreSQL writes finish.

## Search stored documents

```bash
curl --fail --show-error \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"question":"What does the document say about retention?","top_k":5}' \
  http://127.0.0.1:8000/api/v1/search
```

Each result includes the chunk text, filename, page, document ID, chunk index,
and pgvector distance. Smaller distance means a closer vector match; this is a
retrieval diagnostic, not a calibrated answer-confidence score.

## Choices and limits

- `RecursiveCharacterTextSplitter` tries natural text boundaries and keeps
  overlap between adjacent chunks. The initial size and overlap are reasonable
  demo defaults, not measured optimal values. Small chunks are precise but can
  lose context; large chunks retain context but can dilute matching and use
  more tokens per later answer call.
- Amazon Titan Text Embeddings V2 is the default embedding model. The same
  configured embedding object/model is used for document and query vectors.
- LangChain's PostgreSQL vector store keeps vector persistence and similarity
  search in PostgreSQL, which is already part of the planned local setup.
- Raw files are not saved to S3 in this local first version. A new upload gets a
  new document ID; there is no delete endpoint yet.
- PDF text extraction does not OCR scanned pages. A file with no extracted
  text is rejected.
- The API key is a single shared demo key, not user identity or multi-tenant
  access control. Keep this API on a trusted local network.
- There is no answer generation, grounding check, citation verification,
  refusal logic, reranker, evaluation set, or cloud deployment yet. These are
  remaining assessment work.

## Manual checks

The test suite is intentionally deferred for this step. Manually ingest a
small, non-sensitive text/PDF file, then search using a question whose answer is
present in it. Uploading and searching call Bedrock and may incur charges.
