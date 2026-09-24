# Document Q&A API

A small FastAPI service being built in reviewable steps. It currently provides a
health endpoint and the first PostgreSQL/pgvector schema migration. Document
upload, authentication, retrieval, grounded answers, and cloud deployment are
not implemented yet.

## Local development

The backend requires Python 3.12 and uv 0.12.17. Backend code, its environment
template, tests, lockfile and container files are under `backend/`. A future
frontend will live under `frontend/`.

```bash
cd backend
uv sync --frozen
uv run --frozen uvicorn src.main:create_app --factory --reload --host 127.0.0.1 --port 8000 --no-access-log
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
helpers are in `src/db.py`:

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

Bedrock model IDs are set in `backend/src/config.py` and can be overridden with
`BEDROCK_EMBEDDING_MODEL_ID`, `BEDROCK_CHAT_MODEL_ID`,
`BEDROCK_THINKING_MODEL_ID`, and `BEDROCK_RERANKER_MODEL_ID`. AWS region and
credentials come from environment variables. `backend/.env.example` lists the
variable names only; supply real credentials through local environment or a
secret store.

To run the database migration check, provide an empty, disposable local database
whose name begins with `a3_test`:

```bash
cd backend
A3_TEST_DATABASE_URL='postgresql://DB_USER:DB_PASSWORD@localhost:5432/a3_test' uv run pytest -q tests/test_db_migrations.py
```

The test creates and removes the schema. Do not point it at a database containing
data you need to keep. Without this setting, the database test is skipped.

## Checks

```bash
cd backend
uv run --frozen ruff check .
uv run --frozen ruff format --check .
uv run --frozen pytest -q
```

Regular tests make no AWS calls. The database migration test needs the explicit
disposable database setting described above.

## Container

Requires a running Docker engine. On WSL, either enable Docker Desktop integration
or use the Windows client after starting Docker Desktop with `docker.exe desktop
start`.

```bash
cd backend
docker build -t document-qa:local .
docker run --rm --name document-qa -p 127.0.0.1:8000:8000 document-qa:local
```

The container runs as UID/GID 10001. It serves only the health endpoint at this
stage; no AWS clients or database connections start at import time. No cloud
resources are created by local development or tests.

See [progress](docs/progress.md),
[assessment traceability](docs/assessment-traceability.md), and
[decisions](docs/decisions.md) for implementation status and known limitations.
