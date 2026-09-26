# Document Q&A backend

A small FastAPI backend for document ingestion and retrieval-augmented answers.
It uses LangChain for document chunks, Bedrock embeddings and chat models, and
PostgreSQL/pgvector storage and search.

It provides an ingestion route, a search route for inspecting retrieval, and a
chat route that retrieves chunks and uses them to generate a cited answer.
Reranking and a measured evaluation are not implemented yet.

## Requirements

- Python 3.12 and `uv`
- PostgreSQL with the `vector` extension installed
- AWS credentials permitted to invoke the configured Bedrock embedding and chat models
- A database user that can connect to the database and use the `vector` extension

No AWS resources are provisioned by these instructions. Embedding requests are
billable Bedrock calls.

## Configure and run

From `backend/`, copy `.env.example` to `.env` and fill in the local database URL
and a private API key. The app loads settings from that file when it starts.
Use your normal AWS credential chain (for example, `AWS_PROFILE`) for Bedrock
access; AWS credentials themselves are not loaded from this file by the app.

```bash
cd backend
cp .env.example .env
# Edit .env; do not commit it.
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

Open `http://127.0.0.1:8000/docs` to explore the endpoints.

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

## Ask a question and get an answer

The chat route calls the same retrieval function directly; it does not make an
HTTP request to `/api/v1/search`. By default it uses Qwen3 32B. Set
`thinking_mode` to `true` to select GPT-OSS 20B.

```bash
curl --fail --show-error \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"question":"How long are records kept?","top_k":5,"thinking_mode":false}' \
  http://127.0.0.1:8000/api/v1/chat
```

An answered response includes an answer with numbered references such as `[1]`
and source chunks whose `source_id` matches those references. If there are no
retrieved chunks, or the model refuses or omits a valid reference, the endpoint
returns `INSUFFICIENT_CONTEXT` with an empty `sources` list.

Example response:

```json
{
  "status": "ANSWERED",
  "answer": "The records are kept for 30 days [1].",
  "sources": [
    {
      "source_id": 1,
      "source": "retention-policy.pdf",
      "page": 2,
      "text": "Records are kept for 30 days..."
    }
  ]
}
```

This is a first grounding layer, not a guarantee against unsupported claims:
the prompt requests document-only answers, and the API checks that references
map to retrieved chunks. It does not yet verify that each claim is supported by
its cited text or use a tested relevance threshold.

## Choices and limits

- `RecursiveCharacterTextSplitter` tries natural text boundaries and keeps
  overlap between adjacent chunks. The initial size and overlap are reasonable
  demo defaults, not measured optimal values. Small chunks are precise but can
  lose context; large chunks retain context but can dilute matching and use
  more tokens per later answer call.
- Amazon Titan Text Embeddings V2 is the default embedding model. The same
  configured embedding object/model is used for document and query vectors.
- Qwen3 32B (`BEDROCK_CHAT_MODEL_ID`) is used for normal answers; GPT-OSS 20B
  (`BEDROCK_THINKING_MODEL_ID`) is selected by `thinking_mode=true`.
- LangChain's PostgreSQL vector store keeps vector persistence and similarity
  search in PostgreSQL, which is already part of the planned local setup.
- Raw files are not saved to S3 in this local first version. A new upload gets a
  new document ID; there is no delete endpoint yet.
- PDF text extraction does not OCR scanned pages. A file with no extracted
  text is rejected.
- The API key is a single shared demo key, not user identity or multi-tenant
  access control. Keep this API on a trusted local network.
- There is no reranker, measured evaluation set, or cloud deployment yet.
  The prompt and citation-ID check are basic safeguards, not proof that an
  answer is correct or fully supported.

## Manual checks

The test suite is intentionally deferred for this step. Manually ingest a
small, non-sensitive text/PDF file, then call `/api/v1/search` to inspect the
retrieved chunks or `/api/v1/chat` to ask for an answer. Ingestion and search
call the embedding model. Chat calls the embedding model and one chat model, so
these requests may incur charges.
