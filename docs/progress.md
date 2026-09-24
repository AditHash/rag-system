# Progress ledger

## A0 — Inventory and source alignment

Date: 2026-09-20. Status: **PASS** (documentation gate only). Candidate review pending; A1 and all later tasks unstarted.

Requirement: assessment pp1–4 in full; all mandatory outcomes, submission artifacts and walkthrough expectations mapped in R01–R19 of `assessment-traceability.md`.

Files changed: created `docs/baseline.md`, `docs/assessment-traceability.md`, `docs/decisions.md`, and this ledger. Corrected unsupported date claims in `plan.md` introduction and checked A0 only. No application functions or endpoints added.

Flow: inspect repository and existing user files → read all four PDF pages → separate required outcomes from selected mechanisms → map each outcome to future tasks and acceptance evidence. Missing implementation evidence stays explicitly unimplemented; unverified access is not recorded as a successful integration.

Validation:

- `git status --short`, `git ls-files`, `rg --files --hidden -g '!.git/**' -g '!.env'`, and directory inspection: README was the only tracked file; four existing untracked user files; no code/tests/infra. PDF located separately because ignored files are omitted by default.
- `cmp -s AGENTS.md instruct.md`: exit 0, identical guidance.
- `git check-ignore project-information/Aditya_Assessment.pdf`: printed the PDF path, confirming ignored status.
- `sha256sum project-information/Aditya_Assessment.pdf`: `e6db36a597e3992b1e02399d361851d0e08f7b9713ff8e86ba819595164a3584`.
- Tool availability: `python` failed with exit 127; `python3` works. `pdftotext`, pypdf, PyPDF2, fitz and pdfplumber unavailable. No packages installed.
- `python3 /tmp/addroit_read_pdf.py`: exit 0, decoded all four page content streams using embedded font Unicode maps; no unmapped glyphs. Full output reviewed against the matrix. This temporary inspection utility is specific to this PDF, not a general extractor or B3 implementation.
- Manual coverage review: all core-flow bullets, four p2 requirements, p3 AWS guidance/scope/submission items, and p4 walkthrough questions represented. PDF issue date absent; five-day timeline present.
- `python3 /tmp/check_addroit_a0.py`: four check groups passed: 19 unique rows covering pp1–4; four docs present with no trailing whitespace; only A0 checked and product status unimplemented; README/guidance/PDF baseline consistent. Temporary checks are local audit aids, not application unit tests.
- `git diff --check` and `git diff --no-index --check /dev/null <file>` for each new/previously untracked changed Markdown file: no whitespace errors. Explicit file checks needed because ordinary Git diff excludes untracked files.
- Unit/integration tests, pytest, ruff and container build: not run; no application, test suite or project tooling exists. Setup is A1.

Live AWS calls made: **No**. No credentials inspected, resources provisioned, paid inference calls, commits, pushes or deployment.

Tradeoff: documentation-only source alignment makes omissions and uncertainty visible before coding; it does not prove runtime correctness. The chosen container/relational-vector stack offers control and transactional consistency at the cost of idle infrastructure and operational setup compared with a serverless option.

Walkthrough:

- Is ECS required? No. PDF p3 accepts ECS or Lambda and calls its options guidance; ECS Fargate is our selected implementation.
- Is separate-account Bedrock access verified? No. User reports access; A2 must establish authorized authentication, per-model capability and billing, then run approved bounded probes. No success inferred from account readiness.

Known limitations: exact cutoff unconfirmed; live Bedrock integration unverified; no deployed service, measured evaluation, authentication or grounding implementation. Existing ignore policy excludes only project-information; credentials must not be added. All acceptance checks in the traceability matrix are future work.

Next task after explicit user review: **A1 — Configure project**. STOP; do not begin A1 until Aditya approves.

### A0 publication follow-up

User authorized committing and pushing after each step. Publishing A0 does not start A1. Added defensive secret-file exclusions to `.gitignore` before publication; this small security change supersedes the initial baseline's ignore-policy limitation. Assessment PDF remains excluded. Commit scope: `.gitignore`, `AGENTS.md`, `plan.md`, and the four A0 documentation files. Existing duplicate `instruct.md` remains local and untracked to avoid maintaining two copies of the operating contract. Scan staged content for credential patterns and verify the exact staged file list before pushing to the configured GitHub origin. Pattern scanning cannot guarantee absence of every possible secret.

## A1 — Configure project

Date: 2026-09-21. Status: **BLOCKED — container build requires Docker WSL integration**. Python setup implemented and locally validated; A1 checkbox remains open. User approved Phase A work; A0 review is accepted.

Assessment trace: p2 sensible API, p3 compute/API and README requirements; R01, R08, R12. This is foundation work, not fulfillment of ingestion or secured Q&A.

Files: `pyproject.toml`, `uv.lock`, `src/addroit_docqa/`, `tests/test_health.py`, `.env.example`, `.gitignore`, `.dockerignore`, `Dockerfile`, README and task ledgers. Exact direct dependency pins and uv's transitive lock; Python 3.12 selected to match local runtime. uv replaces the illustrative pip commands in the plan. No downstream endpoint scaffolding.

Flow: Uvicorn loads `create_app` with `--factory`; the factory registers typed public `GET /health`; it returns HTTP 200 `{"status":"ok"}` without consulting external services. Unknown routes return 404. Health proves process liveness only. Application authentication and safe error envelopes remain B1 work.

Actual validation:

- Re-read all four PDF pages with `uv run --no-project --with pypdf`; assessment remained local/ignored. pypdf is a temporary inspection dependency, not added to project dependencies.
- Initial `uv add --pin ...` failed: uv does not support that flag. Corrected to `uv add --bounds exact fastapi pydantic uvicorn` and `uv add --dev --bounds exact pytest ruff httpx`; both passed.
- `uv run --frozen ruff check .`: All checks passed.
- `uv run --frozen ruff format --check .`: passed (initial concurrent install run reported 11 files; subsequent final check records the settled project set).
- `uv run --frozen pytest -q`: **2 passed**, 2 dependency deprecation warnings (Starlette httpx migration and anyio BlockingPortal alias). Warnings are not suppressed; revisit when updating the test stack.
- `uv run --frozen python -c 'from addroit_docqa.main import create_app; assert create_app().title == "Addroit Document Q&A"'`: exit 0.
- `UV_PROJECT_ENVIRONMENT=/tmp/addroit-a1-fresh uv sync --frozen --no-editable` plus import from that environment: passed; installed 23 packages, printed `Fresh package import PASS`.
- Temporary local subprocess smoke check started the actual Uvicorn factory on loopback port 18080, received HTTP 200 with exact health body, then terminated it: PASS.
- `docker version` and `docker build -t addroit-docqa:local .`: both exit 1; Docker wrapper reports no Docker command available in this WSL distro and asks for Docker Desktop WSL integration. No image built or container run.

Security/cost: no AWS calls, resource creation or inference. Runtime runs as UID/GID 10001 in the proposed container. Docker context is an allowlist; private assessment and environment files excluded. Access logs disabled. Health takes no secrets. Application routes do not exist yet. Pattern scan before publication is a heuristic, not a guarantee.

Tradeoffs: uv lock gives repeatable Python dependency resolution with one additional development tool. Python 3.12 narrows the supported version for reproducibility (contract requires 3.11+). Base container tags are not digest-pinned and OS layers may change; Docker validation remains outstanding. Small factory isolates app creation for tests and later dependency injection.

Walkthrough: Why `--factory`? It calls `create_app()` to construct the ASGI app; exec-form CMD starts Uvicorn directly so it receives shutdown signals. Does health prove Bedrock works? No: only that this process can answer HTTP requests; dependency readiness needs separate checks.

Next: enable Docker Desktop integration for this WSL distro and rerun build/container smoke test to close A1. Then review A1 before A2. A2 live probes still need credential-type/model/region/owner/billing confirmation and explicit approval. A3 dimensions remain unverified. Phase A is not complete.

### A1 validation completed — 2026-09-22

Status: **PASS**, superseding the earlier Docker blocker. Assessment p3 compute/API and p3 README; R01/R08/R12 foundation only. No new API functions or cloud integrations added.

Inspected Git status (only unrelated untracked `instruct.md`), source/tests, plan, ledger, Dockerfile and relevant assessment page. Initial `docker version` still failed because WSL integration was unavailable; `docker.exe version` also initially failed because Docker Desktop's Linux engine was stopped. Ran `docker.exe desktop start` successfully. The Windows client can build from this repository without changing WSL settings.

Actual checks:

- `uv run --frozen ruff check .`: All checks passed.
- `uv run --frozen ruff format --check .`: 11 files already formatted.
- `uv run --frozen pytest -q`: 2 passed, 2 known dependency warnings, 0.77s.
- `git diff --check`: exit 0.
- `docker.exe version`: Docker Desktop 4.85.0, Linux engine 29.6.2 reachable.
- `docker.exe build -t addroit-docqa:local .`: exit 0; 14 runtime packages installed; image built successfully. Python base resolved to `python:3.12-slim@sha256:2f17fc044b579bab302c2e8054d3a686e2cb9a83de48e70534b94cd8ebbe06a9`; uv base resolved to `ghcr.io/astral-sh/uv:0.12.17@sha256:10787c682e4184e4f290de1171fd4703dc63de99221f10fe1c99002ce7fa9acc`.
- `python3 /tmp/addroit-container-check.py`: three check groups passed. Started `addroit-a1-validation` with `--network none`, verified internal HTTP 200 and exact health JSON; checked UID/GID 10001, no pytest/ruff, and no `.git`, `.env`, `project-information` or `tests` under `/app`; stopped with exit 0 and removed the temporary container. This is an actual local container check, not AWS deployment or an external-client deployment smoke test.

Flow unchanged: Uvicorn factory → typed health route → `{"status":"ok"}`; unknown application routes still return 404. Exec-form startup allows graceful signal handling, now checked. Health intentionally does not test cloud readiness. Runtime-only install reduces image contents; version tags still allow future base-image changes.

Files updated: README, plan, progress, traceability and decisions. No AWS calls, paid resources or inference. Docker Desktop was started and remains available; downloaded local images/build cache remain, temporary test container removed.

Next: **A2**. Requested credential type, region/model IDs, account-owner authorization and billing responsibility without requesting secret values. No live-call approval inferred from the request to continue. Stop at this checkpoint pending A2 prerequisites and explicit approval for a concrete bounded live probe.

## A2 — AWS/Bedrock access probe

Date: 2026-09-22. Status: **BLOCKED — LIVE-BEDROCK invocation permission**.

Credential path tested: AWS access key from the local CSV, account `614934752615`, principal `arn:aws:iam::614934752615:user/Aditya-test`. The separate Bedrock bearer API key was not available to this process and was not inspected.

Read-only checks:

- STS caller identity succeeded.
- `bedrock.list_foundation_models` succeeded in seven regions; `us-east-1` returned 85 text-capable model summaries.
- Catalog included `amazon.titan-embed-text-v2:0` (embedding) and `amazon.nova-micro-v1:0` (text generation).

Approved bounded live checks:

- `bedrock-runtime.invoke_model` with one short text and 256 requested dimensions on `amazon.titan-embed-text-v2:0`: **failed**, `ValidationException: Operation not allowed`.
- `bedrock-runtime.invoke_model` with one short instruction and `max_new_tokens=8` on `amazon.nova-micro-v1:0`: **failed**, `ValidationException: Operation not allowed`.

Only model invocation was billable-capable; both calls were denied before a model response. Response content and credentials were not logged. No resources were created. This is not evidence that the separate bearer API key works; API-key authentication was not tested.

Interpretation: the AWS principal can discover the catalog but cannot invoke these models in `us-east-1`. Account owner must grant/enable model invocation and confirm model access, region, quota and billing, or provide an authorized Bedrock API key whose supported request path is confirmed. Do not substitute Groq or another provider silently and do not claim live Bedrock success.

Next: obtain authorization/model access or the API key details (type only, region and model IDs; never the secret), then run a new explicitly bounded probe. A3 database work can proceed independently after candidate review; A2 remains blocked.

### A2 recheck — 2026-09-24

Using the same local CSV AWS credentials, account identity remained `614934752615`.
`ListFoundationModels` succeeded with 120 model summaries in `us-east-1`; both
`amazon.titan-embed-text-v2:0` and `amazon.nova-micro-v1:0` remain catalogued.
One minimal invocation per model was attempted again. Embedding and generation both
returned `ValidationException: Operation not allowed`. No model output was received,
and no credentials or response content were logged. Status remains **BLOCKED:
LIVE-BEDROCK**. The separate bearer API key remains untested.

## A2 work-account verification — 2026-09-24

Status: **PASS — live Bedrock capabilities verified**.

The authenticated `work-bedrock` profile returned account `451058046921` and the
assumed role `Workmates-SSO-AdminRole`. Region `ap-south-1` was used for models;
reranking used `us-east-1` because that is a supported Cohere Rerank 3.5 region.

Checks:

- Foundation-model catalog: passed, 81 entries.
- Titan V2 `amazon.titan-embed-text-v2:0`: passed; one short input returned a
  1,024-dimensional vector.
- Qwen3 `qwen.qwen3-32b-v1:0`: passed; short Converse request.
- GPT-OSS `openai.gpt-oss-20b-1:0`: passed; short Converse request.
- Cohere `cohere.rerank-v3-5:0`: passed; two short documents, relevant result first.

Only bounded test calls were made. Credentials and response text were not logged.
These were real model calls and may incur small inference charges. The old CSV
account remains invocation-blocked; the work profile is the usable Bedrock path.

Next after review: **A3 — Database schema and migration**. Keep implementation
small: plain SQL, small functions, and direct tests. No source files changed here.

## A3 — PostgreSQL/pgvector schema and migration

Date: 2026-09-24. Status: **PASS** for local schema and migration checks.

Assessment trace: p1 §2 document storage for later ingestion and retrieval (R02),
plus the selected PostgreSQL/pgvector architecture. This is schema groundwork;
no upload, embedding, retrieval endpoint, or AWS deployment is claimed.

Files: added a psycopg 3 connection/migration helper and plain SQL up/down files
under `backend/src/`; tests, dependencies, lockfile, container files, and env
template are under `backend/`. The repo now reserves `frontend/` for later work.
`DATABASE_URL` is read from the environment. Model IDs have defaults in
`backend/src/config.py` and can be overridden by environment variables. AWS
credential variable names are listed in `backend/.env.example`; it contains no
values. Tables cover ingestion jobs, documents, and chunks. `vector(1024)` matches
the verified Titan Text Embeddings V2 probe. The cosine HNSW index supports the
planned similarity operator. `ready_chunks` filters out documents until they are
`READY`. README documents the EC2 PostgreSQL deployment choice without claiming
that an EC2 instance or database has been provisioned.

Flow: an explicit database URL → `connect_database` opens a psycopg connection →
`apply_schema` runs the SQL in one transaction; `rollback_schema` drops the
application view and tables in one transaction while leaving the extension
installed. The schema enforces job/document states, owner-to-job relationship,
unique S3 key, SHA-256 format, positive byte/page sizes, unique chunk ordinal, and
the 1,024-dimensional vector. The `ready_chunks` view excludes processing and
failed documents. Later retrieval code must still scope every query to the caller's
owner. Invalid URLs, missing permissions/extension, SQL errors, and bad data fail
with PostgreSQL/psycopg errors; no silent fallback is used.

Validation (commands run from `backend/`):

- `A3_TEST_DATABASE_URL=postgresql://postgres@127.0.0.1:54329/a3_test uv run --frozen pytest -q tests/test_db_migrations.py` from `backend/`: **2 passed** against a disposable local `pgvector/pgvector:pg18` container. Verified up/down, owner-scoped foreign key, duplicate chunk rejection, invalid document status, 3-vs-1,024 vector rejection, READY-view filtering, and `DATABASE_URL` lookup.
- `uv run --frozen pytest -q` from `backend/`: **4 passed, 1 skipped** (the database integration test skips without its explicit disposable database URL); two existing Starlette/anyio deprecation warnings remain.
- `uv run --frozen ruff check .` and `uv run --frozen ruff format --check .` from `backend/`: passed after the final config formatting.
- `uv build --no-sources` from `backend/`: source and wheel built; inspected wheel to confirm `config.py`, migration helpers, and SQL files are included.
- `docker.exe build -t document-qa:local .` from `backend/`: passed. The first immediate health probe raced container startup and reset; after startup completed, retry returned `GET /health` → HTTP 200, `{"status":"ok"}`. Both temporary test containers were removed.
- The first migration rollback check found that an earlier query had opened an implicit transaction, so the down migration was only inside a savepoint. The integration test now commits its data checks before running down migration, then confirms the tables are gone; the final disposable database run passed.
- Ruff initially reported unsorted imports and one formatting difference during the refactor; both were fixed before the final successful lint/format run.
- No AWS resources or Bedrock calls. README/source name scan and `git diff --check`: clean.

Tradeoff: plain SQL keeps the schema visible and easy to explain; psycopg supplies
direct connections and transactions without an ORM or migration framework. The
cosine HNSW index is convenient for later approximate search but adds index memory
and build cost; exact search may be simpler for a tiny corpus. The extension is
left installed on rollback because it may be shared. No timestamp triggers or
cross-table job-completion rules are added; the ingestion transaction will own
those in later tasks.

Walkthrough:

- Why `vector(1024)`? It matches the verified embedding model output; another
  dimension would be rejected by PostgreSQL and must use a separately migrated
  schema.
- How are READY chunks selected? The view joins chunks to documents and includes
  only `READY`; retrieval still needs an owner filter, as the view alone is not an
  authorization boundary.

Selected deployment database: PostgreSQL with pgvector on a privately reachable
EC2 instance, supplied to the backend through `DATABASE_URL`. Model IDs have
defaults in `backend/src/config.py` and can be overridden by config edits or env.
AWS clients will consume `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, and the
optional `AWS_SESSION_TOKEN` environment values; no real credential values are
stored in the repo. This is a design choice only; no EC2 resources were
provisioned. The existing Windows PostgreSQL
18 installation lacks pgvector. The first integration check used an isolated
local Docker container, not the existing or cloud database. The migration test
only runs when pointed explicitly at an empty local database named `a3_test*`.

## B1 — API-key authentication and request validation

Date: 2026-09-24. Status: **PASS** for the auth helper, validators, and error
response contract. Assessment trace: p2 API authentication and validation (R08);
the `X-API-Key` shape and 10 MiB / 4,000-character limits are plan choices.

`backend/src/auth.py` compares a configured `API_KEY` with the `X-API-Key`
header using constant-time comparison and returns the single `demo-user` owner.
Missing server configuration fails closed with 503; missing or invalid caller
keys receive 401. This is a shared single-principal demo key, not multi-tenant
identity. `backend/src/validation.py` trims and bounds questions and validates
bounded PDF/TXT bytes, MIME, PDF signature and UTF-8 text. `backend/src/errors.py`
returns the stable `{ "error": { "code", "message" } }` envelope and hides
unexpected exception details. The application installs these handlers, but no
production application route is protected yet; ingestion/chat routes will wire
the auth dependency in their own tasks.

Validation (commands from `backend/`):

- `uv run --frozen ruff check .`: passed.
- `uv run --frozen ruff format --check .`: passed, 11 files already formatted.
- `uv run --frozen pytest -q`: **11 passed, 1 skipped**, two existing Starlette /
  anyio deprecation warnings. Tests use local FastAPI test clients and fake key
  values; no AWS, database or paid calls.

The byte validator itself checks 10 MiB after receiving the body; it does not
prevent the HTTP server from buffering a larger multipart body. B8 must enforce a
request-size boundary while reading uploads. A `%PDF-` header is a lightweight
type check, not full PDF integrity validation; B3 extraction handles malformed or
image-only PDFs. Filename sanitization for object keys belongs to the S3 task.

Tradeoff: a shared constant-time-compared key keeps this first auth slice easy to
understand and suitable for a single-user walkthrough. Per-user identity, key
rotation, and multi-tenant authorization need a stronger identity provider and
are not claimed here. User-facing validation messages are stable; unexpected
internal exception details are deliberately hidden.

Walkthrough: What principal does a valid key represent? One fixed `demo-user`,
which later owner-scoped database queries can use. Does the 10 MiB check stop a
large multipart body from reaching the process? Not yet; it checks the parsed
file bytes, and B8 must enforce a streaming request cap.

Next: **B2 — S3 repository**; completion details follow.

## B2 — S3 document storage adapter

Date: 2026-09-24. Status: **PASS** for fake-client adapter checks. Assessment
trace: p3 storage/security guidance (R09); S3 and the object-key shape are
selected architecture choices.

`backend/src/storage.py` adds `S3DocumentStore.put_document` and
`get_document`. The bucket comes from `S3_BUCKET`; boto3 uses its environment and
standard credential chain, and the region comes from `AWS_REGION`. Keys are
generated as `documents/{owner_id}/{document_id}` using a validated owner ID and
UUID; client filenames never enter the key. Uploads include content type and
request AES-256 server-side encryption, without a public ACL. Reads close the
response body and return the stored bytes. AWS/client errors propagate for the
caller to handle; no error is silently treated as success.

Validation (commands run from `backend/`):

- `uv run --frozen ruff check .`: passed.
- `uv run --frozen ruff format --check .`: passed, 13 files formatted.
- `uv run --frozen pytest -q`: **15 passed, 1 skipped**, with two existing
  Starlette/anyio deprecation warnings. Fake client checks covered key scoping,
  payload/type/encryption arguments, absence of ACL, readback, missing bucket,
  invalid input, and S3 exception propagation.
- No S3 network request was made and no bucket was created; therefore the
  account's bucket policy, Block Public Access settings, and IAM permissions are
  unverified.

Tradeoff: S3 holds original bytes while PostgreSQL will hold searchable metadata
and chunks. Deterministic owner/document keys make retries overwrite the same
object and avoid trusting filenames. AES-256 is requested per upload, while
public-access prevention and least-privilege access remain bucket/account policy
responsibilities. No delete operation was added because document lifecycle and
cleanup semantics are not implemented yet.

Walkthrough: Where is source document content stored? In S3, while PostgreSQL
stores metadata and later extracted chunks. Does this adapter itself make a
bucket private? No; it avoids public ACLs and requests encryption, but bucket
Block Public Access and IAM policies must be configured separately.

Next: **B3 — Text extraction**.

## B3 — PDF and text extraction

Date: 2026-09-24. Status: **PASS** for local extraction tests. Assessment trace:
p1 document extraction and source traceability (R02/R04); pypdf and the
page/offset record shape are implementation choices.

`backend/src/extraction.py` exposes `extract_pdf_pages` and `extract_txt`, which
return `ExtractedPage` records. PDFs are extracted one page at a time with
1-based source page numbers; blank pages remain in the result. Character offsets
are measured within each extracted page/text string. TXT is decoded strictly as
UTF-8 and retains its contents. Invalid, encrypted, empty, or textless PDFs and
invalid/blank text raise clear `DocumentExtractionError` messages. Scanned PDFs
are reported as having no extractable text; OCR is outside this MVP.

Validation (commands run from `backend/`):

- `uv run --frozen ruff check .`: passed.
- `uv run --frozen ruff format --check .`: passed, 15 files already formatted.
- `uv run --frozen pytest -q`: **19 passed, 1 skipped**, with two existing
  Starlette/anyio deprecation warnings. Synthetic PDF tests verify page text,
  blank-page numbering, offsets, invalid input and scanned/textless refusal;
  TXT tests verify exact decoded contents, offsets, blank input and UTF-8 errors.
- `uv run --frozen python -c '...extract_pdf_pages(Path("../project-information/Aditya_Assessment.pdf")...)...'`:
  returned four nonempty pages numbered 1–4. Only page counts/lengths were printed;
  the private assessment contents were not included in tests or commits.
- No AWS requests or paid calls.

Tradeoff: pypdf keeps the extraction code small and gives deterministic page
boundaries for later citation metadata. It does not perform OCR, and extracted
text may differ from visual layout, tables, or reading order. Offsets identify
characters in extracted text, not byte positions in the source PDF.

Walkthrough: Why preserve an empty PDF page? Later chunks must retain the PDF's
original page number rather than shifting citations after a blank page. What
does a scanned PDF do? It is refused with a clear extraction error because OCR
is not part of the current scope.

Next: **B4 — Chunker**.

## B4 — Deterministic chunking

Date: 2026-09-24. Status: **PASS** for chunk construction and metadata tests.
Assessment trace: p1 chunking/source citations (R02/R04); 1,000-character chunks
and 150-character overlap are implementation starting points, not PDF mandates.

`backend/src/chunking.py` adds `chunk_pages` and immutable `DocumentChunk`
records. It creates fixed character windows independently on each extracted page,
keeps blank pages out without changing original page numbers, and carries page,
ordinal, document ID, and per-page text offsets. Defaults are 1,000 characters
with 150 characters of overlap; settings are bounded to 10,000 characters and no
more than half the chunk size for overlap. UUIDv5 IDs use the document/source
location and content hash so retrying the same input yields the same ID.

Validation (commands run from `backend/`):

- `uv run --frozen ruff check .`: passed.
- `uv run --frozen ruff format --check .`: passed, 17 files already formatted.
- `uv run --frozen pytest -q`: **27 passed, 1 skipped**, with two existing
  Starlette/anyio deprecation warnings. Tests cover size, overlap, exact offsets,
  blank pages, document scope, stable IDs, invalid settings and invalid offsets.
- No AWS requests, database writes, or paid calls.

Tradeoff: fixed character windows need no tokenizer and give exact traceable
offsets, but they can split a word or sentence and character count is not token
count. The selected settings are initial values and must be tuned using retrieval
evaluation, not described as optimal.

Walkthrough: Why overlap? It repeats a bounded tail at the next chunk's start so
facts crossing a boundary can appear together; it also duplicates storage and
embedding work. Why deterministic IDs? Reprocessing unchanged document text and
settings produces stable keys for safe idempotent persistence.

Next: **B5 — Embedding provider**.

## B5 — Bedrock embedding adapter

Date: 2026-09-24. Status: **PASS** for provider logic under local fake tests;
current live invocation was not run. Assessment trace: p1 embedding flow (R02)
and p4 explanation of embeddings (R15); Titan V2 is the selected model.

`backend/src/embedding.py` adds `BedrockEmbeddingProvider.embed_texts` and
`embed_query`. Both use the configurable Titan model ID, request 1,024 dimensions,
and return vectors validated for exact length, numeric values, and finiteness.
Empty or overly long inputs fail before network access. The boto3 client uses the
configured region and standard environment credential chain. The SDK is set to
one total attempt; application logic retries only throttling and selected server
errors up to three total calls with short exponential delays. Provider errors are
sanitized and no document/query text or credentials are logged.

Validation (commands run from `backend/`):

- `uv run --frozen ruff check .`: passed.
- `uv run --frozen ruff format --check .`: passed, 19 files already formatted.
- `uv run --frozen pytest -q`: **36 passed, 1 skipped**, with two existing
  Starlette/anyio deprecation warnings. Fakes verify model/request payload,
  document/query consistency, empty/oversize inputs, dimension/value failures,
  throttling retry/backoff/exhaustion, and non-retryable failure handling.
- No live Bedrock request was made; fake tests validate adapter behavior but do
  not re-prove current credentials, model access, region quota, or live billing.

Tradeoff: Titan is the shared document/query embedding model selected for the
1,024-dimensional schema. One invoke per text is easy to bound and explain but
has more request latency/cost than a supported batch path. The 30,000-character
input cap is a defensive application limit, not a token-count guarantee.

Walkthrough: Why must query and document embeddings share a model/dimension? Their
vectors must occupy the same semantic space and fit `vector(1024)` for cosine
search. What does retry exhaustion do? It returns a sanitized provider error; it
does not create a fake vector or silently substitute another model.

Next: **B6 — Chunk persistence**.

## B6 — Transactional chunk persistence

Date: 2026-09-24. Status: **PASS** against a disposable local pgvector database.
Assessment trace: p1 persist chunks for retrieval (R02), p1 source metadata
(R04), and the selected PostgreSQL/pgvector design.

`backend/src/chunk_repository.py` adds `upsert_chunks` and
`mark_document_ready`. Upsert validates owner/document association, chunk/vector
count, finite vector values and the 1,024 dimension; it then marks the document
`PROCESSING`, replaces chunks and writes vectors within one transaction. A DB
constraint failure rolls back both the deletion and inserts. The owner-scoped
READY update succeeds only when the expected positive chunk count exists.
Callers can wrap both functions in an outer transaction so chunk replacement and
READY commit together. A document left `PROCESSING` remains hidden from the
`ready_chunks` view.

Validation (commands run from `backend/`):

- `A3_TEST_DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:54329/a3_test_b6 uv run --frozen pytest -q tests/test_db_migrations.py`: **2 passed** against a disposable `pgvector/pgvector:pg18` container. The test verified repeat writes keep two rows, failed replacement restores prior rows, wrong owner cannot write or mark READY, incorrect expected count cannot mark READY, and the view reveals chunks only after the correct transition.
- The first integration run caught use of `Connection.executemany`; switched to the psycopg cursor API before the passing run.
- With the same test DB enabled, `uv run --frozen pytest -q`: **39 passed**, two existing Starlette/anyio deprecation warnings.
- `uv run --frozen ruff check .`, `uv run --frozen ruff format --check .`, and `git diff --check`: passed.
- The temporary container was stopped and removed. No AWS resources or paid calls.

Tradeoff: replacing the whole chunk set is easy to retry and restores the old set
on failure, but it rewrites unchanged chunks. Stable UUIDs plus `UNIQUE(document_id,
ordinal)` prevent duplicates. The selected HNSW index is maintained by PostgreSQL
as rows are replaced; larger ingestion batches may need measured tuning.

Walkthrough: When does content become searchable? Only after the owner-scoped
READY transition sees the expected stored chunk count. What if one insert fails?
The replacement transaction rolls back, and the document stays hidden for retry.

Next: **B7 — Ingestion orchestrator**.

## B7 — Ingestion orchestration

Date: 2026-09-24. Status: **PASS** for the local end-to-end service flow with
fake storage/model clients and disposable pgvector. Assessment trace: p1
upload-to-index flow (R02), with S3, Bedrock and PostgreSQL as selected choices.

`backend/src/ingestion.py` adds `create_job` and `process_job` for one document per
job. `create_job` persists a pending job and processing document. `process_job`
loads the owner-scoped record, advances stages, fetches the object, extracts PDF
pages or UTF-8 text, chunks it, verifies the embedding model ID, embeds, then
atomically writes chunks, marks the document READY, and completes the job. Each
external I/O step runs outside a database transaction. Failures set both job
and document to `FAILED`; only a safe stage-specific error is stored. Re-entering
a completed job returns its chunk count without another embedding call. An
atomic claim rejects a second worker when the job is already PROCESSING. Failed
jobs can retry using deterministic chunk IDs; a process crash can leave a job
stuck PROCESSING until a later recovery mechanism is added.

Validation (commands run from `backend/`):

- `A3_TEST_DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:54329/a3_test_b7 uv run --frozen pytest -q tests/test_db_migrations.py`: **2 passed** against disposable pgvector. The integration helper exercised the full service with fake S3/embedding, completed-job re-entry, active-job duplicate rejection, embed failure, sanitized status, hidden failed chunks, and successful retry.
- With the same disposable DB enabled, `uv run --frozen pytest -q`: **40 passed**, two existing Starlette/anyio deprecation warnings.
- `uv run --frozen ruff check .`, `uv run --frozen ruff format --check .`, and `git diff --check`: passed.
- The first integration run caught the psycopg cursor API issue recorded in B6; after correction all end-to-end cases passed. The local container was stopped and removed.
- S3 and Bedrock were fakes; no AWS requests/resources or inference charges.

Tradeoff: the flow is intentionally one document per job. Short DB transactions prevent holding locks while S3/Bedrock respond, at the cost of several brief connections/stage writes. Atomic claim prevents concurrent duplicate work, but jobs are not durable queue messages and a process crash can strand PROCESSING status; B8/B10 must handle and document that runtime boundary.

Walkthrough: What prevents partial chunks from becoming searchable? The final transaction commits all replacement rows, READY, and job completion together; the view excludes every non-READY document. What happens after an embedding failure? The job records only the embedding stage, the document remains hidden, and retry reuses the same job/document IDs.

Next: **B8 — Authenticated ingestion endpoint**.

## B8 — Authenticated ingestion endpoint

Date: 2026-09-24. Status: **PASS** for the local API contract using fake cloud
providers and disposable PostgreSQL. Assessment trace: p1 ingestion flow and
p2 validated/authenticated API; R02 and R08. The endpoint is a selected
implementation detail; the assessment requires document ingestion and API
security, not this exact route framework.

`backend/src/routes.py` mounts `POST /api/v1/ingest`. It authenticates the
request, accepts one PDF/TXT multipart file, sanitizes the basename, enforces a
10 MiB file cap and a total-body cap (including requests without
`Content-Length`), creates the persistent job/document records, uploads the
object, and returns IDs with `202 PENDING`. The route then schedules
`process_job` as a synchronous FastAPI background task. In production ASGI, the
response is sent before that background task runs. The work shares the API
process and is not durable; a restart can interrupt it. S3 upload and database
job creation happen before the response. AWS clients are constructed lazily.

Flow: multipart bytes → API-key owner → bounded input/type checks → persistent
job and private S3 key → HTTP 202 → background extraction/chunk/embed/persist.
Validation returns stable 413/415/422 errors; DB/storage configuration or
operations fail with sanitized 503. On storage failure, the created job is
marked failed. The middleware returns 400 for malformed content length and
413 when the request body exceeds the cap.

Files/functions: `backend/src/routes.py` defines the route, injected
dependencies and body limiter; `backend/src/main.py` mounts them;
`backend/src/ingestion.py` accepts stable IDs and exposes sanitized failure
marking; `backend/src/storage.py` exposes deterministic object-key generation.
README and OpenAPI tests now match the implemented route.

Validation (from `backend/`):

- `uv run --frozen ruff check .`: passed.
- `uv run --frozen ruff format --check .`: 25 files already formatted.
- `uv run --frozen pytest -q`: **45 passed, 1 skipped**, two existing
  Starlette/anyio deprecation warnings.
- With disposable `pgvector/pgvector:pg18` database
  `a3_test_b8`, `A3_TEST_DATABASE_URL=... uv run --frozen pytest -q`:
  **46 passed**. This also exercised the existing migration/ingestion DB
  integration tests. The temporary database container was stopped and removed.
- Route tests cover valid upload and queued call, API key rejection, unsupported
  and malformed input, file/request caps, storage failure sanitization, and
  chunked body size enforcement. S3 and embedding use fakes; no AWS request,
  resource, or inference call was made. `git diff --check`: passed.

Security/cost: no upload content or secret is returned in errors. The
single-key auth maps to one demo principal, so this is not production identity
or multi-tenant authorization. A configured bucket, DB, AWS credentials/role,
and authorized Bedrock are required for real ingestion. No AWS spend occurred.

Tradeoff: FastAPI `BackgroundTasks` keeps this API small and proves the 202
request path, but it is not a queue and can lose work on process termination.
SQS plus a separate ECS worker improves delivery/retry isolation at added
resource and operational cost; durable queue choice remains conditional on the
time/cost budget. The current route writes the object before returning 202,
which avoids acknowledging an upload that was never stored but keeps S3 latency
on the request path.

Walkthrough: Why 202 instead of 200? The file and job have been accepted while
the indexing work may still be running. Does this guarantee durable async
execution? No; the in-process background task may be interrupted. Why cap the
entire body as well as the file? Multipart boundaries and fields also consume
request memory.

Next: **B9 — Scoped ingestion status endpoint**. User authorized continuous
work; the previous per-task review stop is waived for this run.

## B9 — Scoped ingestion status endpoint

Date: 2026-09-24. Status: **PASS** for local HTTP contract and PostgreSQL
owner-scope integration. Assessment trace: p1 ingestion status and p2 secure
API; R02/R08. Persisting status is part of the selected job design; a dedicated
HTTP route is our implementation choice.

`GET /api/v1/ingest/{ingestion_id}/status` requires the same API key as upload.
`backend/src/job_repository.py:get_job_status` selects the job only where both
the requested UUID and authenticated `owner_id` match, and returns associated
document IDs, status, stage, completed/total counts, and the already-sanitized
error. The route maps unknown and cross-owner jobs to the same 404 envelope and
database failures to a sanitized 503. The response progress is counts, not a
percentage estimate. Status remains readable from PostgreSQL after an API
process restart; that does not make the in-process ingestion task durable.

Flow: path UUID + API key → owner-scoped query → typed status JSON. Invalid UUIDs
are rejected by FastAPI validation; missing/cross-owner IDs are indistinguishable
404s; connection/query errors return 503. Output has `status`, `stage`,
`progress.completed_documents`, `progress.total_documents`, `document_ids`, and
nullable sanitized `error`.

Validation (commands run from `backend/`):

- `uv run --frozen ruff check .`: passed.
- `uv run --frozen ruff format --check .`: 26 files already formatted.
- `uv run --frozen pytest -q`: **51 passed, 1 skipped**, two existing
  Starlette/anyio deprecation warnings.
- With disposable `pgvector/pgvector:pg18` database `a3_test_b9`,
  `A3_TEST_DATABASE_URL=... uv run --frozen pytest -q`: **52 passed**. The DB
  integration verified a job returns its expected state/document ID to its
  owner and returns no result for another owner. Temporary DB container stopped
  and removed.
- API tests cover all four statuses, response fields, API-key enforcement,
  unknown/cross-owner 404 behavior, sanitized database failure, and OpenAPI.
  `git diff --check`: passed.
- No AWS calls, resources, or Bedrock inference were made.

Security/cost: status lookup is scoped in SQL rather than relying on the
`ready_chunks` view or hiding IDs in the client. A single shared key remains a
demo authentication limitation. PostgreSQL reads add no AWS spend; no cloud
service was contacted.

Tradeoff: count-based progress is honest for the current one-document job and
does not imply a percentage of work completed. More detailed per-stage or
per-chunk progress would require additional persisted state and writes. Job
status can survive an API restart, but a `PROCESSING` job may still need
recovery because B8 uses in-process execution.

Walkthrough: Can one caller see another owner's job by guessing its UUID? No;
the owner is included in the database predicate, and both absent and
unauthorized IDs return 404. Does persisted status prove the worker survived a
restart? No; only status persists. The background work can stop while status
remains `PROCESSING`.

Next: **C1 — Retrieval repository and owner-scoped cosine search**.

## C1 — Query embedding boundary

Date: 2026-09-24. Status: **PASS** for deterministic local validation.
Assessment trace: p1 question-to-vector retrieval flow; R02. Titan V2 and
1,024 dimensions are selected model/schema choices; the assessment requires
retrieval, not this provider or dimension.

`backend/src/query_embedding.py:embed_query` receives question text, an
embedding provider, and the model ID used for indexed documents. It rejects
blank input before any provider call, fails if query and indexed model IDs
differ, calls the provider's same-model query method, then verifies the
1,024-value numeric finite vector. It returns the checked vector for C2 cosine
search. Provider errors propagate to the caller; no substitute model or dummy
vector is created. `backend/src/embedding.py` already implemented the Bedrock
adapter's query method; this increment adds the explicit retrieval boundary and
its contract checks.

Validation (commands run from `backend/`):

- `uv run --frozen ruff check .`: passed.
- `uv run --frozen ruff format --check .`: 28 files already formatted.
- `uv run --frozen pytest -q`: **55 passed, 1 skipped**, two existing
  Starlette/anyio deprecation warnings.
- New tests cover matching-model happy path, empty text, model mismatch before
  provider invocation, and invalid vector dimension. All use a fake; no Bedrock
  inference or AWS call was made. `git diff --check`: passed.

Security/cost: no question is logged or sent during unit tests; no cost-bearing
service is contacted. A wrong model configuration fails before inference.

Tradeoff: checking the configured/indexed model ID prevents semantically
incompatible vector comparison, and dimension/finite validation protects the
database operator. This adds a small validation layer in front of the provider;
the fixed model ID is still configuration-level evidence, while C2 must ensure
retrieved documents use that indexed model.

Walkthrough: Why must query and document vectors use the same model? Equal
dimensions alone do not mean their coordinates represent the same semantic
space. What does a model mismatch do? It fails before a Bedrock request instead
of returning an untrustworthy similarity ranking.

Next: **C2 — Owner-scoped pgvector cosine retrieval**.

## C2 — Owner-scoped cosine retrieval

Date: 2026-09-24. Status: **PASS** for unit tests and disposable PostgreSQL/
pgvector integration. Assessment trace: p1 retrieval from indexed document
chunks and p1 source metadata; R02/R04. PostgreSQL/pgvector and cosine search
are selected architecture choices.

`backend/src/retrieval.py:retrieve_candidates` validates its query vector and
uses a parameterized query joining chunks to documents. SQL filters by exact
owner ID, document `READY` status, and the expected embedding model; optional
UUIDs add a scoped document filter. It orders by pgvector `<=>` cosine distance,
then chunk ID for stable ties, and clamps requested `top_k` to 1–20 (default
10). Returned rows include chunk/document IDs, original filename, page, ordinal,
text, cosine distance, and `similarity = 1 - distance`. The caller can request
zero allowed documents with `document_ids=[]`, which returns no candidates.

Flow: validated query vector + owner/model/document scope + top-k → SQL
cosine-distance order → typed candidates with source metadata. Invalid vector
dimension or non-finite values fail before SQL; the DB only returns READY rows
matching the owner/model filters. Database errors propagate for the service/API
layer to map safely.

Validation (commands run from `backend/`):

- `uv run --frozen ruff check .`: passed.
- `uv run --frozen ruff format --check .`: 30 files already formatted.
- `uv run --frozen pytest -q`: **63 passed, 1 skipped**, two existing
  Starlette/anyio deprecation warnings.
- With disposable `pgvector/pgvector:pg18` database `a3_test_c2`,
  `A3_TEST_DATABASE_URL=... uv run --frozen pytest -q`: **64 passed**. Fixed
  orthogonal unit vectors confirmed result ordering, distances 0 and 1, and
  similarities 1 and 0. The integration also confirmed source page/filename,
  top-k cap, optional document scope, model filter, and exclusion of foreign
  owner, FAILED and PROCESSING documents. Temporary DB container stopped and
  removed.
- Unit tests check similarity transformation, returned metadata, SQL scope
  predicates, explicit document filters, empty allowed document list, k bounds,
  and invalid vector rejection. `git diff --check`: passed.
- No AWS service or paid inference was used.

Security/cost: the owner and document filters remain database predicates, so a
client cannot obtain another principal's chunks by supplying its document UUID.
The local DB test is free aside from local compute; no external services were
called.

Tradeoff: pgvector's `<=>` returns cosine **distance**, so the response computes
`1 - distance` to report cosine similarity. This score ranks candidates; it is
not a calibrated probability or refusal threshold. The schema has an HNSW
cosine index, but this small fixture does not measure index use or large-corpus
recall/latency. An exact scan may be faster for a tiny corpus; index and
partition strategy need measurement on representative data.

Walkthrough: Why filter `READY` in the query if there is already a view? The
repository joins the base tables to enforce owner/model/document predicates in
the same SQL statement; `READY` still explicitly excludes partial ingestion.
What does similarity 0.8 mean? Only that the embedding vectors have that
cosine relationship under this transform; it is not an 80% chance the answer is
supported.

Next: **C3 — Optional reranker adapter**, then C4 evidence/refusal gate.

## C3 — Optional Bedrock reranker

Date: 2026-09-24. Status: **PASS** for fake-client adapter and fallback
contracts. Assessment trace: p1 improves relevance as a possible retrieval
technique; reranking is optional and is our selected design choice. Cohere
Rerank 3.5 capability was verified earlier under the authorized work profile;
this task made no live inference call.

`backend/src/reranking.py` uses the Bedrock Agent Runtime `rerank` operation,
not the model-generation `InvokeModel` request shape. It sends exactly one text
query and at most 20 candidate chunks, maps returned indexes back to the
server-held `RetrievalCandidate` objects, and exposes the model's relevance score
under that name without treating it as calibrated confidence. Result count is
bounded to 1–20 (default 5). The model ARN is constructed from the configured
model ID and `BEDROCK_RERANKER_REGION`; this region defaults to `us-east-1`
separately from `AWS_REGION` because model capabilities differ by region. The
client has bounded connect/read timeouts and disables SDK retries.

`rerank_candidates` returns an explicit `reranked` flag. If the adapter returns a
sanitized provider error or malformed indexes/scores, it returns the original
top candidates in retrieval order, with `relevance_score=None` and
`fallback_reason="provider_error"`. It never passes provider error text to the
API. Empty candidate input makes no request; blank query and invalid oversized
inputs fail validation.

Validation (commands run from `backend/`):

- `uv run --frozen ruff check .`: passed.
- `uv run --frozen ruff format --check .`: **32 files already formatted**.
- `uv run --frozen pytest -q`: **74 passed, 1 skipped**, two existing
  Starlette/anyio deprecation warnings.
- Unit tests use only fake model clients; they verify the Bedrock operation
  payload/region ARN, index mapping, ranking order, score field, empty input,
  request bounds, provider failure fallback, and malformed-index fallback. No
  paid reranking call or other AWS request was made.
- `git diff --check`: passed.

Security/cost: only retrieved candidate text and the query are sent to Bedrock
when this optional adapter is invoked; deployment therefore needs explicit
cross-account permission for the Agent Runtime rerank action and the supported
model region. The adapter is optional and was not called by these tests.

Tradeoff: reranking can improve ordering after vector recall but adds an extra
model request, latency, and inference cost. It only sees the initial candidates
and cannot recover a relevant chunk omitted by vector search. Failure falls
back to vector order with no false score claim. The actual effect must be
measured in the evaluation set before keeping it enabled in production.

Walkthrough: Why is the score field called `relevance_score`, not probability?
The API labels it as the model output; it is not calibrated for answer truth.
What happens if AWS denies reranking? The caller gets a marked pass-through in
the original cosine order, and there is no made-up rerank score.

Next: **C4 — Pre-generation evidence/refusal gate**.

## C4 — Pre-generation evidence gate

Date: 2026-09-24. Status: **PASS** for local deterministic heuristic tests.
Assessment trace: p1 grounded answers and refusal of unsupported queries; R03.
The PDF requires refusing unsupported questions; the cosine threshold and
decision schema are our implementation choices.

`backend/src/evidence.py:assess_evidence` receives the vector-retrieval
candidates. With no candidates it returns `INSUFFICIENT_CONTEXT/NO_CANDIDATES`;
when all candidate cosine similarities fall below the configured threshold it
returns `INSUFFICIENT_CONTEXT/BELOW_THRESHOLD` and an empty candidate list.
Otherwise, it returns `EVIDENCE_FOUND` with only candidates meeting the
threshold. The initial threshold is `EVIDENCE_MIN_COSINE_SIMILARITY=0.55`, set
in `config.py` or overridden by environment. Invalid threshold/scores fail
closed with `ValueError`.

This gate performs no generation call; C7 will branch on the decision and C8
will return the stable refusal response. `EVIDENCE_FOUND` means a vector score
cleared a heuristic gate; it does not establish that the source entails an
answer. Threshold and relevance behavior must be evaluated with the real
ground-truth set in D1/D2.

Validation (commands run from `backend/`):

- `uv run --frozen ruff check .`: passed.
- `uv run --frozen ruff format --check .`: **34 files already formatted**.
- `uv run --frozen pytest -q`: **81 passed, 1 skipped**, two existing
  Starlette/anyio deprecation warnings.
- Tests cover no candidates, weak low-similarity evidence,
  threshold boundary, filtering weak candidates, and invalid thresholds/scores.
  The injected input is deterministic; no Bedrock calls, DB access, or paid
  AWS resources were used. `git diff --check`: passed.

Security/cost: weak/empty evidence can be stopped before a paid generation
request. The score threshold may still accept irrelevant text or reject a valid
paraphrase; no zero-hallucination or calibrated-confidence guarantee is made.

Tradeoff: one minimum-similarity threshold is small and explainable, but
similarity is not answer probability and a single score cannot test claim
entailment. A lexical coverage or verifier may improve handling but can add
false refusals, provider cost, and complexity; only add such checks when the
ground-truth evaluation demonstrates benefit. C6 still validates source IDs and
citations.

Walkthrough: What happens when no evidence is found? The gate returns
`INSUFFICIENT_CONTEXT`, so the orchestrator will not call the generator. Does a
score above `0.55` mean 55% confidence? No; it is cosine similarity used by a
tunable heuristic, and the threshold is not yet calibrated.

Next: **C5 — Context builder, strict prompt, and structured generator parser**.

## C5 — Grounded prompt and structured generation adapter

Date: 2026-09-24. Status: **PASS** for deterministic fake-client behavior.
Assessment trace: p1 answer from evidence, unsupported-query refusal, and safe
source use; R03/R04/R05. Using Bedrock Converse, Qwen/GPT-OSS, JSON source
serialization and the exact response schema are architecture choices.

`backend/src/generation.py:build_grounded_prompt` assigns request-local source
IDs (`S1`, `S2`, …), then serializes the question and only the IDs plus chunk
text as JSON. Filenames, pages, owner IDs and other citation metadata stay on
the server. The system instruction limits answers to evidence, treats every
document as untrusted data, rejects embedded commands, asks for no hidden
reasoning, and requests exactly `status`, `answer`, `cited_source_ids`.
Question, source count, context characters and output size are bounded.

`BedrockGenerator.generate` calls Converse once with the selected model ID,
temperature 0.1 and a 1,024-token output cap. It parses text blocks only and
returns optional token counts when present. `parse_generated_answer` accepts
only a strict JSON object with the exact keys and known status values; markdown,
malformed content, duplicate IDs, empty answers, and inconsistent refusal
citations fail with sanitized `GenerationError`. An ANSWERED result may still
contain a missing or unknown source ID; C6 owns the server-side citation check.
The adapter does not retry a generation failure, avoiding hidden repeated
inference charges.

Validation (commands run from `backend/`):

- `uv run --frozen ruff check .`: passed.
- `uv run --frozen ruff format --check .`: **36 files already formatted**.
- `uv run --frozen pytest -q`: **98 passed, 1 skipped**, two existing
  Starlette/anyio deprecation warnings.
- Fake-client tests cover context escaping with an injected instruction,
  server-only metadata, input bounds, supported/refusal response schemas,
  malformed JSON/fields/status, duplicate IDs, Converse request/model/token
  bounds, malformed response and usage, and sanitized upstream failure. No AWS
  request or paid generation call was made. `git diff --check`: passed.

Security/cost: the prompt makes documents untrusted and refuses to request
hidden reasoning, but prompts are not a security boundary by themselves.
Structured output and later server-side ID binding are required; text may still
be unsupported despite valid JSON. Generation costs one bounded model request;
the evidence gate must run first.

Tradeoff: the common Converse API keeps Qwen and GPT-OSS invocation simple, and
strict JSON makes parsing predictable. Prompt-only schema adherence can fail;
the parser then stops the answer rather than trying to salvage prose. A native
structured-output feature could improve reliability if supported by both
selected models and the account, but would add model-specific behavior.

Walkthrough: Why send IDs and evidence text but not filenames/pages? The model
can select evidence IDs, while the service must bind original citation metadata
from trusted DB rows. Does valid JSON guarantee a grounded claim? No; C6 checks
IDs and source assembly, and evaluation still measures factual support.

Next: **C6 — Server-side citation validation and source assembly**.

## C6 — Citation validation and source assembly

Date: 2026-09-24. Status: **PASS** for deterministic unit contract and pgvector
metadata integration. Assessment trace: p1 verifiable original-source citations;
R04/R05. Citation IDs and output shape are our implementation choices; source
traceability is required.

`backend/src/citations.py:validate_citations` binds the model's source IDs to
the exact candidate mapping supplied to the prompt. An ANSWERED response with
no IDs, duplicate IDs, or IDs absent from the retrieved set raises
`CitationValidationError`. A valid response produces citations using only the
server's retrieval records: `document_id`, original filename, page, character
offsets, and chunk excerpt. A refusal must have no cited IDs and returns an
empty source list. C2 now selects start/end offsets from the database with the
chunk so the output can point within the original page/file.

Flow: parsed status/answer/source IDs + request-local source map → existence and
uniqueness checks → server-assembled `VerifiedAnswer`. Model-supplied metadata
is not part of `ParsedAnswer` and cannot override filename/page/offsets. Unknown
or missing IDs fail closed; the later orchestrator will map that validation
failure to a bounded refusal. Even valid source IDs only show that chunks were
retrieved; they do not prove semantic entailment.

Validation (commands run from `backend/`):

- `uv run --frozen ruff check .`: passed.
- `uv run --frozen ruff format --check .`: **38 files already formatted**.
- `uv run --frozen pytest -q`: **105 passed, 1 skipped**, two existing
  Starlette/anyio deprecation warnings.
- With disposable `pgvector/pgvector:pg18` database `a3_test_c6`,
  `A3_TEST_DATABASE_URL=... uv run --frozen pytest -q`: **106 passed**. This
  verified retrieved page and text offsets against persisted chunk metadata.
  Temporary container stopped and removed.
- New unit tests cover valid multi-source output, source ordering, filename/page/
  offset/excerpt binding, empty-source refusal, missing, duplicate and bogus IDs,
  invalid ID types, and refusal-with-citation rejection. No AWS request or paid
  call was made. `git diff --check`: passed.

Security/cost: only the generator's opaque ID selection is trusted; citation
metadata is rebuilt from server-owned DB results. There is no additional model
call or inference cost.

Tradeoff: ID binding prevents fabricated file/page references, but does not
verify that an excerpt entails every answer sentence. An entailment verifier or
bounded retry could reduce some unsupported claims but adds latency/cost and
can still be wrong; the measured evaluation should determine if either is
useful.

Walkthrough: Can the model invent page 99 and have it returned as a citation?
No; only source IDs are parsed, and the service looks up the page from the
retrieved candidate. Does a valid source ID prove the sentence is true? No; it
proves only that the cited chunk was retrieved and must be checked in evaluation
or by a separate evidence-support method.

Next: **C7 — End-to-end answer orchestrator**.

## A1 runtime command follow-up — 2026-09-24

Status: **PASS** locally. The backend adds `backend/main.py` so `uv run main.py`
starts the Uvicorn app. The Dockerfile installs locked dependencies using
`uv sync --frozen --no-dev --no-install-project`, copies the runtime source, and
uses `CMD ["uv", "run", "main.py"]`; `UV_NO_SYNC=1` prevents startup-time
resynchronization. `WEB_CONCURRENCY` sets Uvicorn worker processes (default 1).
This is process concurrency, while FastAPI dispatches synchronous route handlers
and dependencies to its thread pool. ECS CPU/memory and task scaling have not
been configured; no claim is made that multiple workers improve throughput for
this workload without measurement.

Validation:

- `uv run --frozen ruff check .`: passed.
- `uv run --frozen ruff format --check .`: 23 files already formatted.
- `uv run --frozen pytest -q`: **39 passed, 1 skipped**, with two existing
  Starlette/anyio deprecation warnings. The new test verifies the worker setting.
- `uv run --frozen main.py` from `backend/`, then `curl --fail --silent --show-error http://127.0.0.1:8000/health`: returned `{"status":"ok"}`; the process shut down cleanly.
- `docker.exe build -t enterprise-rag:local .` from `backend/`: passed. Build ran `uv sync --frozen --no-dev --no-install-project` and installed 23 runtime dependencies without building/installing the backend project.
- Ran the resulting container and called `GET /health`: HTTP 200 with `{"status":"ok"}`. The temporary container was stopped and removed.
- `UV_NO_SYNC=1` is the documented uv environment setting that prevents the startup `uv run` from syncing the venv. No AWS resources or inference calls were used.
