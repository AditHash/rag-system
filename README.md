# Enterprise RAG Platform

This repository is the backend foundation for an enterprise-grade retrieval-
augmented generation (RAG) system. Document Q&A is one capability within that
system. The selected architecture is FastAPI, private S3, PostgreSQL/pgvector,
Amazon Bedrock, and ECS Fargate. These describe the target; they are not all
implemented or deployed yet.

The current backend provides a health endpoint and an authenticated one-file
ingestion endpoint. It stores the upload in S3, creates a PostgreSQL job, and
returns `202 PENDING` before background extraction, chunking, embedding, and
index persistence run. Status lookup, retrieval, grounded answer generation,
and cloud deployment remain to be implemented.

## Local development

The backend requires Python 3.12 and uv 0.12.17. Backend code, its environment
template, tests, lockfile and container files are under `backend/`. A future
frontend will live under `frontend/`.

```bash
cd backend
uv sync --frozen
uv run main.py
```

Check the service:

```bash
curl --fail http://127.0.0.1:8000/health
# {"status":"ok"}
```

Health reports that the API process is running. It does not check PostgreSQL or
cloud services. The interactive API docs are at `/docs`.

## Database

The schema is in `backend/src/migrations/initial_schema.sql`; the rollback is in
`backend/src/migrations/rollback.sql`. The migration creates jobs, documents and
chunks, with embeddings fixed at 1,024 dimensions. It requires PostgreSQL with
the pgvector extension installed. The `ready_chunks` view only exposes chunks
whose documents are marked `READY`; retrieval must also filter by owner. Migration
helpers are in `backend/src/db.py`:

```python
from src.db import apply_schema, connect_database

with connect_database() as connection:
    apply_schema(connection)
```

`connect_database()` reads `DATABASE_URL` from the environment. For deployment,
the URL will point to PostgreSQL on the user's EC2 instance; the database should
be reachable over the private network. Do not put credentials in source control.
The down migration removes the three tables and keeps the pgvector extension
because other applications may use it.

`POST /api/v1/ingest` requires the `X-API-Key` header and one multipart field
named `file`. Set `API_KEY` in the local environment; a valid key currently maps
to one demo principal, so this is not multi-tenant identity management. The
route accepts PDF or UTF-8 TXT up to 10 MiB and bounds the complete multipart
body before parsing it. It validates and stores the upload, creates a persistent
job, then schedules ingestion with FastAPI `BackgroundTasks`. A response means
the job was accepted, not completed. This in-process task can be interrupted by
a restart and is not durable queue delivery. A real ingestion needs a configured
`S3_BUCKET`, `DATABASE_URL`, AWS credentials/role, and Bedrock access; local
endpoint tests replace those providers with fakes. Question input is capped at
4,000 characters for the planned chat endpoint.

Bedrock model IDs are set in `backend/src/config.py` and can be overridden with
`BEDROCK_EMBEDDING_MODEL_ID`, `BEDROCK_CHAT_MODEL_ID`,
`BEDROCK_THINKING_MODEL_ID`, and `BEDROCK_RERANKER_MODEL_ID`. AWS region and
credentials come from environment variables. `backend/.env.example` lists the
variable names only; supply real credentials through local environment or a
secret store.

`backend/src/storage.py` uses the standard boto3 credential chain, including AWS
credential environment variables, and reads the bucket name from `S3_BUCKET`.
Object keys are generated from the owner and document IDs; original filenames are
not used as keys. The adapter requests server-side AES-256 encryption and does
not set a public ACL. Bucket-level Block Public Access and IAM permissions still
must be configured separately; no S3 bucket has been created or tested here.

`backend/src/extraction.py` returns one text record per PDF page with 1-based
page numbers, preserving blank pages so later citations keep their original page
mapping. TXT is decoded as UTF-8 and represented as one record. Offsets count
characters in each extracted text record. Scanned and password-protected PDFs
are rejected; OCR is not implemented.

`backend/src/chunking.py` splits each text record into fixed-size character
windows with overlap. Defaults are 1,000 characters and 150 characters of
overlap; callers can set both values within bounded limits. Each chunk keeps its
document, page, ordinal, and text offsets, and receives a deterministic ID for
safe retries. This simple splitter may cut a sentence or word at a boundary; the
parameters need evaluation against the target documents.

`backend/src/chunk_repository.py` writes vectors and chunk metadata in PostgreSQL
transactions. A document remains hidden from `ready_chunks` until its owner-scoped
READY transition confirms the expected chunk count.

`backend/src/ingestion.py` connects storage, extraction, chunking, embedding,
and persistence for one document per job. The mounted ingestion route completes
the S3 upload and job creation, returns `202 PENDING`, then starts embedding in
FastAPI's in-process background task. Its database connection factory keeps
transactions short around external I/O. A failed stage stores only the stage
name and marks the document `FAILED`; retrying a completed job returns its
stored chunk count without repeating inference, and an atomic claim rejects
simultaneous processing attempts. A worker left in `PROCESSING` after process
termination currently needs recovery. The status route and durable queue remain
pending.

`backend/src/embedding.py` contains the Bedrock Titan V2 adapter. It uses the
same model and fixed 1,024 dimensions for document and query embeddings, validates
each response before returning it, and retries throttling at most twice after
the initial attempt. A live embedding request is not part of local tests.

To run the database migration check, provide an empty, disposable local database
whose name begins with `a3_test`:

```bash
cd backend
A3_TEST_DATABASE_URL='postgresql://DB_USER:DB_PASSWORD@localhost:5432/a3_test' uv run pytest -q tests/test_db_migrations.py
```

The test creates and removes the schema. Do not point it at a database containing
data you need to keep. Without this setting, the database test is skipped.

## Design notes

**Why 1,024 embedding dimensions?** The selected Titan Text Embeddings V2
configuration returned a 1,024-value vector in the approved live probe. The
database column is `vector(1024)`, so documents and questions must use the same
model and dimension. Changing either requires a schema migration and re-embedding
stored chunks.

**Does `ready_chunks` enforce access control?** No. It hides chunks until their
document is `READY`, so incomplete ingestion is excluded from retrieval. Each
retrieval query must also filter by the authenticated caller's `owner_id`. The
view does not restrict access to the underlying tables or identify the caller.

## Checks

```bash
cd backend
uv run --frozen ruff check .
uv run --frozen ruff format --check .
uv run --frozen pytest -q
```

Regular tests make no AWS calls. Ingestion endpoint tests use fake S3, database,
and embedding dependencies. The database migration test needs the explicit
disposable database setting described above.

## Container

Requires a running Docker engine. On WSL, either enable Docker Desktop integration
or use the Windows client after starting Docker Desktop with `docker.exe desktop
start`.

```bash
cd backend
docker build -t enterprise-rag:local .
docker run --rm --name enterprise-rag -p 127.0.0.1:8000:8000 enterprise-rag:local
```

The container runs as UID/GID 10001. It serves the health and authenticated
ingestion routes. No AWS clients or database connections start at import time;
ingestion clients are initialized lazily when the route is called. No cloud
resources are created by local development or tests.

The Docker image syncs locked runtime dependencies without installing/building
the local project package, then starts with `uv run main.py`. `UV_NO_SYNC=1`
prevents a second environment sync at container startup. `WEB_CONCURRENCY`
controls Uvicorn worker processes and defaults to 1. FastAPI runs synchronous
route handlers and dependencies in a thread pool; Uvicorn workers are separate
processes, not threads. For ECS, begin with one worker per task and scale task
count horizontally; increase workers only after matching them to the task's CPU
and memory and measuring load. No ECS sizing or scaling resources are configured.

See [progress](docs/progress.md),
[assessment traceability](docs/assessment-traceability.md), and
[decisions](docs/decisions.md) for implementation status and known limitations.
