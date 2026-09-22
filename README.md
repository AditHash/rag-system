# Addroit Document Q&A

Assessment project using FastAPI, ECS Fargate, S3, PostgreSQL/pgvector and Amazon
Bedrock. These are selected design choices; see [plan.md](plan.md).

Current implementation: a local FastAPI application with `GET /health` only.
Ingestion, authentication, retrieval, grounding, database and AWS integration are
not implemented. A1 local and container validation passed on 2026-09-22.
The proposed architecture in the plan is not a deployed system.

## Local development

Prerequisites: Python 3.12 and uv 0.12.17. Dependencies, including transitive
versions and hashes, are recorded in `uv.lock`; commit lock changes when updating
packages. uv installs the package into `.venv` using the `src` layout.

```bash
uv sync --frozen
uv run --frozen uvicorn addroit_docqa.main:create_app --factory --reload --host 127.0.0.1 --port 8000 --no-access-log
```

From another terminal:

```bash
curl --fail http://127.0.0.1:8000/health
# {"status":"ok"}
```

OpenAPI is at `/openapi.json`; local interactive docs are at `/docs`.
Health is public process liveness, not a database or Bedrock readiness check.
There are no document/query routes yet; requests to them return 404. The unified
application error envelope and API-key enforcement will arrive in B1.

`.env.example` contains reserved names only; A1 does not load these settings.
No credentials are needed to run or test health. Never commit `.env`, credentials,
or private documents. `project-information/` stays ignored.

## Checks

```bash
uv run --frozen ruff check .
uv run --frozen ruff format --check .
uv run --frozen pytest -q
uv run --frozen python -c 'from addroit_docqa.main import create_app; assert create_app().title == "Addroit Document Q&A"'
```

Tests use an in-process HTTP client and make no AWS or Bedrock calls.

## Container

Requires a running Docker engine. On WSL, enable Docker Desktop integration for
this distro, or use the Windows client as validated here: run `docker.exe desktop
start`, then substitute `docker.exe` for `docker` in the commands below.

```bash
docker build -t addroit-docqa:local .
docker run --rm --name addroit-docqa -p 127.0.0.1:8000:8000 addroit-docqa:local
```

The image installs runtime dependencies only and runs as UID/GID 10001. Its exec
form command starts Uvicorn directly, calls `create_app` via `--factory`, and
listens on port 8000 inside the container. No cloud clients start with the app.
Access logs are disabled to avoid retaining raw query strings. The Docker build
context allowlist excludes the assessment, Git metadata, local settings and tests.
Base images use version tags, not immutable digests; dependency locks do not make
OS layers immutable. The local image passed health, UID/GID, excluded-file, runtime-dependency and
graceful-shutdown checks. No image has been deployed to AWS.

See [progress](docs/progress.md), [traceability](docs/assessment-traceability.md),
and [decisions](docs/decisions.md). Paid AWS resources and live Bedrock calls need
explicit approval.
