# Assessment traceability

Source: local `project-information/Aditya_Assessment.pdf`, all four pages reviewed on 2026-09-20. The PDF controls requirements; `plan.md` controls our implementation choices. All checks below are future acceptance evidence, not executed tests.

A0 documentation gate: **PASS**. Every requirement is mapped below; **all product requirements remain unimplemented and unverified**.

| ID | PDF location | Requirement / expectation | Planned tasks | Required evidence |
|---|---|---|---|---|
| R01 | p1 §1; p3 §3 | Small real service deployed live on AWS; use managed services where reasonable | A1, D4–D5 | Actual deployment and fresh-client callable API |
| R02 | p1 §2 | Upload documents; extract, chunk, embed, store for retrieval | A3, B1–B9 | Extraction/page, chunk, embedding, transaction and ingestion HTTP tests; completed real upload |
| R03 | p1 §2 | Natural-language query retrieves relevant chunks and generates grounded answer | C1–C8 | Retrieval ordering/scope and full query tests; real answer |
| R04 | p1 §2 | Each answer cites a verifiable original source | B3–B4, C6, D5 | Server-bound source metadata; invalid-citation rejection; visual source comparison |
| R05 | p1 §2; p2 grounding | Refuse absent answers; demonstrate grounding mechanism (highest priority) | C4–C8, D1–D2, D5 | Unsupported/adversarial question tests; pre-generation gate; post-generation verification and measured refusal |
| R06 | p2 evaluation; p3 §4 | Ground-truth question/expected-answer set and measured results; PDF suggests 10–15 | D1–D2 | Human-reviewed 10–15 cases per plan, actual scores/config, failure analysis; no mock metrics |
| R07 | p2 cost; p3 cost note | Explain expensive components and cost-reduction decisions; bound model usage | A2, D2–D4, D6 | Approved per-call/recurring estimates, actual call counts, limits and cleanup |
| R08 | p2 API | Clean upload/query API with basic auth or API key and input validation | A1, B1, B8–B9, C8, D3 | Auth, input caps, safe errors and HTTP contracts |
| R09 | p3 §3 permissions/storage | Defensible AWS storage/access choices; least-needed IAM access and no hardcoded credentials | A2, B2, D3–D4 | Private S3 and scoped role policies, secret scan, approved storage/auth checks |
| R10 | p3 §3 scope note | Explain any incomplete AWS work and how to finish it | A2, D4, D6–D7 | Honest blocker ledger, limitations and remaining actions |
| R11 | p3 §4 | Submit callable live service with short example | D4–D7 | Real URL, fresh-client example and safe authentication handoff |
| R12 | p3 §4 | GitHub code and short README: running and design decisions | A1, D6–D7 | Verified run instructions, repository access, decisions and secret check |
| R13 | p3 §4 | Short architecture diagram of actual AWS setup | D4, D6 | Diagram matches deployed resources; proposed diagram is not evidence |
| R14 | p1 §1; p4 §5 | Live walkthrough for Aasim and Suhas: upload, grounded answer/source, refusal | D5–D6 | Recorded dry run and source verification |
| R15 | p4 §5 | Explain request path, bottlenecks, costs, chunking, embeddings, retrieval and any reranking | B4–B7, C1–C3, D6 | Defense notes, chunk-size tradeoff, model/dimension and retrieval rationale |
| R16 | p4 §5 | Explain precise grounding/refusal mechanism and scoped Bedrock authentication | A2, B5, C4–C6, D3, D6 | Actual auth path and evidence-gate walkthrough with limitations |
| R17 | p4 §5 | Explain evaluation construction, measurements, failures and small-set blind spots | D1–D2, D6 | Results and failure analysis; proposed hardening |
| R18 | p4 §5 | Explain hardest decision/problem and scaling failure at 500K documents | D6 | Decision history and reasoned throughput, indexing, capacity and cost discussion; no scale claim |
| R19 | p1 timeline | Five-day assessment timeline | D7 | Confirm exact cutoff externally; issue date absent from PDF |

## Required outcomes versus selected mechanisms

- AWS-native live deployment is required. PDF p3 explicitly calls its service list guidance, not a mandate. ECS Fargate, FastAPI, S3, PostgreSQL/pgvector and Bedrock are the user's selected stack; RDS hosting and ingress topology still require cost approval.
- The plan selects PDF **and** UTF-8 TXT, versioned endpoints, `X-API-Key`, persistent status, READY-only retrieval, server-built citations and layered grounding. The PDF does not prescribe these exact interfaces or algorithms.
- Evaluation is required. The plan adopts 10–15 cases from the PDF's suggested small-set size and adds explicit metrics.
- Async ingestion is a plus in PDF p3. SQS/separate worker is conditional; reranking and Guardrails are optional. Neither is required for assessment compliance. Any demo worker must disclose restart/loss limitations.
- AgentCore, OCR, frontend and GraphRAG are outside the selected scope. A running service, measured results and correct refusal take priority over optional features.

## A0 source reconciliation

The plan previously attributed a 17 September issue date to the PDF and asserted a 20 September target had passed. Neither claim is established by the supplied PDF. Corrected the introduction only; task ordering and frozen interfaces remain unchanged.

## A1 checkpoint — 2026-09-21

R01/R08/R12 foundation now exists: installable FastAPI package, typed liveness route,
locked dependencies, README commands, two passing local HTTP tests, clean lint and
format checks, and successful fresh install/import. The Dockerfile is written but
its build is **BLOCKED** by missing Docker WSL integration. No deployed service,
authenticated application routes, ingestion, retrieval or evaluation exists.
A0's statement of no implementation is historical; mandatory product outcomes
remain unmet. A1 is not checked off until container validation passes.

## A1 gate closed — 2026-09-22

**PASS**, superseding the prior container blocker. R01/R08/R12 foundation now has
actual local container build evidence plus HTTP health, non-root runtime,
private-file exclusion and graceful-shutdown checks. Two local HTTP tests and
lint/format checks passed again. No AWS deployment or secured Q&A is claimed.
See the progress ledger for exact commands and the Docker Desktop Windows-client
workaround. A2 access probes have not run.

## A2 checkpoint — 2026-09-22

R07/R09/R16 access evidence is **BLOCKED: LIVE-BEDROCK**. Catalog discovery via
the CSV AWS principal works, but one minimal embedding invocation and one minimal
generation invocation each returned `ValidationException: Operation not allowed`.
The separate bearer API key has not been tested. No Bedrock success, model output,
or paid result is claimed. See the A2 ledger for exact model IDs and scope.

## Model decision checkpoint — 2026-09-24

Selected stack: Titan Text Embeddings V2 (1,024 dimensions), Qwen3 32B for normal
generation, GPT-OSS 20B for routed complex questions, and Cohere Rerank 3.5 for
optional candidate reranking. These are design selections, not live-access
evidence; a later A2 checkpoint verified bounded real calls for all four
capabilities using the authorized work-account profile.

## A2 gate closed — 2026-09-24

**PASS** using the authorized `work-bedrock` profile in account `451058046921`.
Titan, Qwen3, GPT-OSS and Cohere reranking each passed a bounded real call. The
earlier CSV account's invocation denial remains a separate limitation.

## A3 database schema — 2026-09-24

**PASS** for schema and migration validation. Direct SQL creates ingestion jobs,
documents and chunks, uses `vector(1024)` with a cosine HNSW index, and exposes a
`ready_chunks` view that filters out documents until they are `READY`. The local
pgvector integration test verified migration up/down, foreign-key owner scope,
chunk uniqueness, vector dimension, document status checks, and the READY view.
Owner filtering in retrieval SQL remains a C2 requirement; the view is not a
replacement for authorization checks.

## B1 authentication and validation — 2026-09-24

R08 **PASS** for reusable auth, validators, and the stable error envelope.
`X-API-Key` is compared in constant time, maps to one demo principal, and fails
closed if the server has no configured key. Unit/HTTP tests cover valid, missing
and invalid keys, empty/oversize questions, accepted and rejected PDF/TXT input,
oversize files, and sanitized errors. No production application route is
protected until its endpoint task wires in the dependency. The helper's 10 MiB
file-byte cap does not constrain multipart buffering; B8 must add a streaming
request limit. See `docs/progress.md` for exact commands and limitations.

## B2 S3 storage adapter — 2026-09-24

R09 **PASS** for a locally tested adapter only. S3 object keys are generated
from owner/document IDs, upload requests ask for AES-256 server-side encryption,
and the adapter does not set public ACLs. Fake-client tests verify calls,
round-trip bytes and failure propagation. No bucket was created or contacted;
private bucket policy, Block Public Access and IAM are still unverified and must
be completed before a live deployment. See `docs/progress.md` for the exact
boundary and tests.

## B3 PDF/TXT extraction — 2026-09-24

R02/R04 **PASS** for local extraction behavior. PDF pages are preserved with
1-based page numbers, including blank intermediate pages; TXT uses strict UTF-8.
Synthetic fixtures test exact page mapping, offsets, malformed/textless PDFs and
invalid text. A read-only extraction check on the local four-page assessment
confirmed page numbers 1–4 without recording its text. Scanned PDFs are rejected
because OCR is out of scope. See `docs/progress.md` for exact commands and
limitations.

## B4 chunking — 2026-09-24

R02/R04 **PASS** for deterministic local chunk construction. Tests verify
character boundaries, configured overlap, page/offset metadata, blank-page
handling and repeatable document-scoped IDs. Chunk size and overlap are
implementation starting points requiring retrieval evaluation. See
`docs/progress.md` for tests and tradeoffs.

## B5 embeddings — 2026-09-24

R02 **PASS** for local adapter behavior. The Titan V2 adapter requests and
checks 1,024 dimensions for both document and query text, with bounded throttling
retries. Tests use a fake Bedrock client; no live call or current credential
verification is claimed. A previous bounded model probe is recorded under A2.
See `docs/progress.md` for exact tests and current limitations.

## B6 chunk persistence — 2026-09-24

R02/R04 **PASS** against disposable local pgvector. Replacing chunk rows is
transactional, owner-scoped, and tested for retries, rollback, expected counts,
and READY-view visibility. Live AWS storage and ingestion remain untested. See
`docs/progress.md` for exact database, test, and cleanup evidence.

## A1 runtime command follow-up — 2026-09-24

R01/R12 local run path **PASS**. Both development and Docker now launch through
`uv run main.py`; the Docker environment avoids installing the project package.
`WEB_CONCURRENCY` controls Uvicorn processes, with FastAPI's thread pool handling
synchronous route functions. This is a local container/runtime choice; no ECS
deployment, task sizing, or load test is claimed. See the progress ledger for the
Docker smoke result.

## B7 ingestion orchestration — 2026-09-24

R02 **PASS** for a local fake-provider flow using disposable PostgreSQL/pgvector.
The test covered successful storage-to-READY processing, idempotent completed-job
re-entry, active-job duplicate rejection, sanitized mid-embedding failure, hidden chunks, and retry. No live S3
or Bedrock call was made. Authenticated HTTP upload and durable async delivery
remain later tasks. See `docs/progress.md` for exact results and limits.

## B8 authenticated ingestion endpoint — 2026-09-24

R02/R08 **PASS** for local API contract. `POST /api/v1/ingest` authenticates
with the configured API key, accepts one bounded PDF/TXT multipart upload,
persists a job, stores the object, and returns `202` before in-process
background indexing. Request body limits cover both declared and chunked
content. Tests use fakes for S3 and embeddings; database integration ran with a
disposable local pgvector instance. This single demo principal is not
multi-tenant authorization, and in-process background execution is not durable.
No live AWS call or paid resource was used. The status endpoint and retrieval
remain incomplete; see `docs/progress.md` for exact commands, outputs and
failure handling.

## B9 scoped ingestion status — 2026-09-24

R02/R08 **PASS** locally. The authenticated status route returns persisted
status, stage, count-based progress, document IDs and sanitized failure detail.
Its PostgreSQL query filters by both job ID and principal; unknown and
cross-owner IDs both return 404. Tests cover every job status and verify owner
isolation against disposable local pgvector. Status persists across API process
restarts, but B8 in-process task execution is not durable. No live AWS calls or
resources were used. See `docs/progress.md` for exact test evidence.

## C1 query embedding — 2026-09-24

R02 **PASS** for local embedding boundary behavior. The retrieval helper rejects
empty questions and mismatched configured model IDs before provider calls, then
validates the 1,024-value finite vector returned by the injected provider. Unit
tests use a fake; no Bedrock inference was made for this increment. Model and
dimension are selected design choices recorded separately. See
`docs/progress.md` for exact tests and limitations.

## C2 owner-scoped retrieval — 2026-09-24

R02/R04 **PASS** locally against pgvector. Candidate SQL scopes by owner,
`READY`, and embedding model, supports optional document IDs and bounded top-k,
and returns source metadata plus cosine distance/similarity. Orthogonal fixed
vectors verified ordering and the distance-to-similarity transform; integration
excluded foreign-owner, failed and unready documents. The HNSW index is present
but index use, recall, and latency at scale are not measured. This repository
function is not yet wired into chat. See `docs/progress.md` for exact validation.

## C3 optional reranker — 2026-09-24

Optional R02 ranking enhancement **PASS** for local adapter behavior. The
Bedrock Agent Runtime adapter sends the bounded query/candidate set and maps
returned indexes to original server-held candidates. It explicitly marks
pass-through fallback and omits rerank scores when the provider fails. Fake
tests validate request shape and failure handling; this increment made no live
Bedrock call. Account/model capability was separately verified under A2. The
reranker remains optional and must be compared in the actual evaluation before
production use.
