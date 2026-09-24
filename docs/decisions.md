# Decisions and unresolved choices

Recorded at A0, 2026-09-20. These are selected design directions, not implemented capabilities.

| Decision | Reason and tradeoff | State |
|---|---|---|
| Follow PDF outcomes and plan task order; stop after each task | Keeps increments reviewable and defensible; adds explicit review checkpoints | Active workflow |
| Present the project as an enterprise-grade RAG system | Document Q&A is a core capability; the broader system includes ingestion, retrieval, grounded generation and deployment | Target framing; implementation remains incremental |
| ECS Fargate + FastAPI | User-selected container API; greater control over runtime/worker lifecycle than Lambda, with idle cost and networking overhead | Selected, not built |
| Private S3 + PostgreSQL/pgvector | Raw documents in object storage; transactional metadata/vectors in PostgreSQL | Selected; PostgreSQL will run on EC2, with `DATABASE_URL` supplied to the backend through environment configuration. No EC2 resources provisioned |
| Amazon Bedrock through separately authorized account credentials | Matches user access situation; adds auth, ownership and billing boundaries | Bounded work-account probes passed in A2; deployed ECS credential path remains unimplemented |
| Layered grounding and server-built citations | Meets highest-priority refusal/verifiability requirements; citation existence alone does not prove factual support | Planned, no mechanism implemented |
| SQS worker conditional; reranker/Guardrails optional | Protects core scope and budget. Skipping durable queue requires explicit interruption limitations; optional model calls add cost/latency | Undecided/off until implemented and verified |
| Deterministic local fakes; separately approved live checks | Local testing without inference charges; fake success cannot establish real AWS access or evaluation quality | Planned test policy |
| Start the API through `uv run main.py`; runtime image installs dependencies only | Avoid a package build/install step for this simple service; keep the container command directly runnable | Implemented locally; no deployment |

Pending: confirmed deadline, deployed ECS credential path, account-owner authorization for ongoing inference, PostgreSQL EC2 sizing/networking, worker mode, ingress and approved budget. No secrets belong in these records.

## A1 implementation choices — 2026-09-21

Python 3.12 matches the available interpreter; uv 0.12.17 manages exact direct pins
and a transitive lock. A `src` package and `create_app` factory support isolated
construction and future injected providers. Only process liveness is implemented.
Docker uses runtime-only dependencies, non-root UID 10001 and an allowlisted build
context. Version-tagged base images can change; digest pinning and an actual build
remain deployment/reproducibility considerations. Container validation is blocked
by unavailable Docker Desktop integration in WSL; no deployment claim is made.

### A1 validation follow-up — 2026-09-22

Started the existing Docker Desktop installation and used `docker.exe` from WSL
to build and validate the Linux container. This closes the local build blocker
without changing WSL integration settings. The README documents this alternative.
Runtime health, UID/GID, file exclusions and graceful shutdown passed; no AWS
resources were touched. Base-image tags remain mutable, with resolved digests
recorded in the progress ledger for this validation.

## Locked RAG model stack — 2026-09-24

Embedding: Amazon Titan Text Embeddings V2 (`amazon.titan-embed-text-v2:0`), fixed at
1,024 dimensions. Normal generation: Qwen3 32B (`qwen.qwen3-32b-v1:0`). Thinking
generation: OpenAI GPT-OSS 20B (`openai.gpt-oss-20b-1:0`). Optional reranking:
Cohere Rerank 3.5 (`cohere.rerank-v3-5:0`). Ordinary questions route to Qwen;
complex or conflicting questions route to GPT-OSS. This is model routing, not a
promise to expose hidden reasoning. Retrieval starts cosine top-10 and reranks to
top-5. Model IDs have defaults in `backend/src/config.py` with environment
overrides. AWS credentials will be consumed from `AWS_ACCESS_KEY_ID`,
`AWS_SECRET_ACCESS_KEY`, and optional `AWS_SESSION_TOKEN`; no real values belong in
the repository. Bounded model probes passed using the authorized work-account
profile; application adapters and deployed ECS credentials are still unimplemented.

## A3 database schema — 2026-09-24

Use direct PostgreSQL SQL migrations and psycopg 3, with no ORM or migration
framework. Store Titan embeddings as `vector(1024)`. A cosine HNSW index supports
the selected similarity operator. The `ready_chunks` view filters out documents
that are still processing; retrieval must also scope every query by owner. The
down migration removes application tables and view but leaves the pgvector
extension installed because it can be shared by other applications.

## B4 chunking — 2026-09-24

Start with 1,000-character chunks and 150-character overlap. Character windows
are easy to bound and explain, and keep source offsets exact; token-aware or
semantic splitting would add a tokenizer/dependency before the evaluation set
shows it is needed. Chunk IDs are deterministic UUIDv5 values scoped to the
document and source location/content, making retries repeatable. These defaults
are starting points, not measured optimal settings; evaluation may change them.

## B5 embeddings — 2026-09-24

Use Titan Text Embeddings V2 at 1,024 dimensions for both document and query
text. The local database schema is fixed to `vector(1024)`, and an earlier bounded
probe verified this model returns that dimension when requested. The adapter
checks each returned vector against the schema before handing it to persistence.
It performs one request per text and has three total application attempts for
throttling/server failures, with SDK retries disabled so that bound is explicit.
This is simple and predictable but may add latency and call cost for large
documents; batching/throughput tuning belongs after end-to-end evaluation.

## B6 chunk persistence — 2026-09-24

Replace a document's chunk set inside one PostgreSQL transaction on retry. This
keeps stable IDs idempotent and rolls back deletion if any insert violates a
constraint. Set the document to `PROCESSING` before replacement so `ready_chunks`
does not expose a partial set. `mark_document_ready` is owner-scoped and checks
the expected chunk count. The orchestrator should call both operations within one
outer transaction to commit the completed set and READY state together; a crash
before then leaves the document hidden and retryable.

## A1 runtime command and ECS concurrency — 2026-09-24

Use `uv run main.py` for local and container startup. The Docker build installs
locked dependencies with `--no-install-project`, then `UV_NO_SYNC=1` makes the
same simple command launch without rebuilding/syncing the application package.
`WEB_CONCURRENCY` configures Uvicorn worker processes, defaulting to one. FastAPI
dispatches synchronous route handlers/dependencies to a thread pool; worker
process count is not thread count. ECS task count is the preferred horizontal
scale unit; choose process count only after task CPU/memory and load are measured.

## B7 ingestion orchestration — 2026-09-24

Keep external S3/Bedrock calls outside PostgreSQL transactions. Persist each
stage separately, then commit chunk replacement, document READY, and job
COMPLETED together in one final transaction. Failure stores only the stage name
and leaves the document hidden. A repeated completed job is an idempotent no-op;
a failed job can be retried with deterministic chunk IDs. This is currently a
single-document job with injected providers; durable execution and request
idempotency belong to later endpoint/worker tasks. A conditional update claims
only PENDING or FAILED jobs to prevent concurrent workers from processing one
job; stuck PROCESSING recovery remains a worker/operations concern.

## B8 ingestion HTTP endpoint — 2026-09-24

Accept one multipart document at a time and create the job/document before
uploading to S3. Return `202 PENDING` after storage succeeds, then use FastAPI's
in-process `BackgroundTasks` for the existing ingestion service. Both the file
and complete multipart request have strict size bounds; count body bytes even
if the client omits `Content-Length`. This small path avoids blocking on
embedding but is not durable: process termination can interrupt indexing. SQS
and a separate ECS worker are an option if the demo needs durable delivery and
budget/time allow; do not describe the current behavior as queued or durable.
