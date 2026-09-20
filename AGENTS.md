# AGENTS.md — Codex Operating Contract for Addroit Assessment

> Save this file as **`AGENTS.md`** in the repo root (uppercase); keep `plan.md` next to it and include `Aditya_Assessment.pdf` if available. Read all three before acting. The PDF is authoritative for *requirements*; `plan.md` contains **our selected implementation**. Never mislabel ECS/SQS/reranking/Guardrails as mandated by the PDF.

## Mission

Build a small, real AWS-native document Q&A API for Addroit: upload, extract, chunk, embed, store, retrieve, grounded answer with verifiable citations, and refuse unsupported queries. Planned: ECS Fargate + FastAPI + private S3 + PostgreSQL/pgvector + authorized Bedrock credentials from another AWS account. Implement in **individual explainable, verifiable increments**. The candidate must be able to defend every important function during a live walkthrough. Deliver a callable service, GitHub README, measured 10–15-case evaluation, and accurate architecture diagram. Refer to assessment pp. 1–4 and `plan.md` §1 for traceability.

## Mandatory per-task protocol — DO NOT SKIP OR BATCH

1. **Inspect** `plan.md`, `docs/progress.md`, applicable PDF section, existing code/tests and `git status`. Do not overwrite user work. Determine next *one* unchecked task (e.g., B3) or ask which one to tackle. If prerequisite is `BLOCKED`, say so; avoid pretending dependency works.
2. **Propose** brief contract: PDF requirement, functions/endpoint and inputs/outputs, files to change, failure cases, tests, costs/security implications. Mark what is assessment-mandated versus our architecture choice. For paid AWS action seek explicit approval before execution.
3. **Implement only that increment** with typed, readable Python, meaningful names, small focused functions, predictable error handling and no unnecessary framework. Do not scaffold downstream endpoint logic in bulk. When changing interfaces, update associated contract and tests.
4. **Validate** with relevant unit tests, integration tests when disposable infrastructure exists, formatting/lint, and real AWS tests *only if approved*. Report commands and ACTUAL output. Never treat mocked results as successful Bedrock access, ECS deployment or measured evaluation.
5. **Explain to Aditya**: how the new function works (inputs → steps → outputs), where it is called, at least one failure path, why the choice matches the assessment and an alternative/tradeoff. Show one sample call/response for an endpoint; give 1–2 interview questions and concise answers. Be especially thorough for auth, embedding model/dimensions, cosine search, reranking, grounding, citations and cross-account IAM.
6. **Record** task status `PASS|FAIL|BLOCKED` with files, tests/results, limitations and traceability in `docs/progress.md` and `docs/assessment-traceability.md`. Make source/infra diagrams reflect only actual implementation. **STOP and request candidate review** before beginning another task. Do not claim the full project is done after one slice.

If user explicitly asks for multiple tasks, still create separate checkpoints and validation for each; stop at each critical external/billable action.

## Hard requirements and priority

The PDF explicitly prioritizes grounded answers and refusal; those are more important than polish. Checklist: document ingestion; retrieval; citations to verifiable original source; unsupported-query refusal; small actual ground-truth evaluation; cost discussion; authenticated, validated API; AWS-native live deployment; least-privilege IAM; README + architecture diagram; live demo and explanations. Reconcile work to PDF page-specific traceability. If anything remains incomplete, state it directly; never falsify completion.

**Priority order:** mandatory working flow → grounding/refusal → evaluation → live deployment/security/docs (plan these in parallel by critical path) → optional reranker → optional Guardrails/worker enhancements. AgentCore, agent workflows, OCR, frontend and GraphRAG are out of scope unless Aditya changes scope. Reranker and SQS are choices, not PDF requirements; document if omitted. Do not accidentally turn a 5-day assignment into a platform project.

## AWS and money — explicit approval gates

- Our AWS account exists but **Bedrock access is not yet established**. We have possible credentials from another AWS account. First determine **Bedrock bearer API key vs AWS access/secret vs assume-role** without seeing or printing secrets. Standard boto3 SigV4 and bearer API-key authentication are not interchangeable. Cross-account permission is NOT inherited from our ECS task role; implement the compatible authenticated adapter only after confirming owner authorization, supported API paths, model/region access, quotas and billing responsibility.
- Separate inference capabilities: embedding model, generation model, reranker and Guardrails may have different permissions. Verify each with an approved minimal call; do not infer access from console display or from one successful model.
- Never use the candidate's employer AWS account or third-party billing without permission. Before any resource creation show region, rough recurring + per-call costs and cleanup; wait for approval. Budgets alert, not cap. Cost-bearing items include ECS Fargate, ALB, RDS, VPC networking/NAT, Secrets Manager, CloudWatch and Bedrock. Avoid NAT Gateway by default unless justified.
- Local unit tests use deterministic fake providers. Optional live tests are clearly marked and bounded. If Bedrock unreachable, report `BLOCKED: LIVE-BEDROCK` and continue independent local tasks; do not secretly use another LLM and claim Bedrock success.
- Use IAM task role/execution role correctly, least-privilege S3/queue/DB permissions, and Secrets Manager for third-party keys where necessary. No hardcoded credentials or public S3. Don't log secret headers, content of uploaded documents, or raw sensitive queries.

## Exact API and data boundaries

See `plan.md` §2.3–2.4. Enforce versioned routes, no unreviewed renaming:

- `GET /health`: simple health, optionally separate dependency readiness.
- `POST /api/v1/ingest`: authenticated bounded multipart PDF/TXT → `202` persisted job ID + document IDs + PENDING. Do NOT perform all embedding before responding if claiming async.
- `GET /api/v1/ingest/{ingestion_id}/status`: authenticated scoped persistent state, stage, progress, sanitized error; never reveal another principal's job.
- `POST /api/v1/chat`: authenticated validated question + optional permitted document IDs + bounded top_k → `ANSWERED` with answer and verified `sources`, or `INSUFFICIENT_CONTEXT` with non-fabricated message/empty sources. Retrieval diagnostics, if exposed, must be separately identified and correctly scoped.
- Consistent safe error JSON; proper HTTP 401/404/413/415/422/503, and docs/OpenAPI matching real behavior. Treat status lookup, document filtering and source metadata as security boundaries.
- Jobs: `PENDING|PROCESSING|COMPLETED|FAILED`; documents queryable only when `READY`. Store document/owner/checksum/S3 key and chunk IDs/page/ordinal/text/vector/model version. Embed query and docs with identical model/dimension. Never invent PDF pages or citations in an LLM response.

## Grounding and refusal: mandatory layers

1. Scope-filter pgvector retrieval to READY, authorized docs; check no evidence/low relevance. Cosine distance ≠ calibrated answer probability. Use tunable threshold/coverage validated against evaluation set; report false positives/negatives.
2. Optional reranker of initial candidates, then bounded context. If inaccessible, explicit passthrough; don't fabricate scores or claim a reranker is running. Distinguish retrieved candidates from sources actually cited.
3. Build strict context-only prompt, numbered server-assigned source IDs, and structured answer/refusal schema. Source documents are untrusted instructions; prompt alone is not a safety guarantee.
4. Parse response and check every cited ID exists in retrieved/authorized evidence. Assemble filename/page/excerpt **server side**, never let LLM supply unverifiable metadata. Missing/invalid citations or unsupported claims → bounded retry or refusal. Citation existence does not guarantee factual support; consider evidence verifier and test limits.
5. Tests must cover supported fact, paraphrase, absent answer/general knowledge, adversarial similar passage, conflicting chunks, injected document instruction, bogus citation, empty corpus, wrong owner and upstream failures. Do not report zero hallucination as a guarantee.
6. Bedrock Guardrails can supplement this only if access, latency, cost and actual behavior have been checked; not a substitute for application grounding.

## Engineering conventions

- Python 3.11+; FastAPI, Pydantic, type hints, dependency injection for providers, small modules. No unnecessary LangChain/agents dependency unless explicitly approved. Stable error and output schemas.
- `pytest` + `ruff` baseline. Prefer explicit adapters: `S3Store`, `JobRepository`, `DocumentRepository`, `ChunkRepository`, `EmbeddingProvider`, `Reranker`, `Generator`, `GroundingVerifier`. Keep cloud code isolated and mockable. Reuse clients; timeouts, bounded retries, backoff for throttling; no runaway paid calls.
- Text extraction preserves page numbers; reject unextractable PDFs clearly. Chunk IDs stable and retry safe. DB transaction semantics prevent ready-before-complete; repeated ingestion must not produce duplicate chunks.
- Retrieval SQL must parameterize document IDs/principal and cap k. Test cosine direction and vector dimension, error status vs insufficient evidence, and safe serialization. Keep endpoints thin; orchestration in services; dependencies injectable in tests.
- SQS and a separate ECS worker are preferred for durable async if time/budget allow; otherwise explicitly disclose that a demo background task may be interrupted at restart. Never call FastAPI BackgroundTasks durable or assume HTTP 202 is a queue.
- Secrets ignored in `.gitignore`; `.env.example` contains keys/names only. Uploaded PDFs, evaluation inputs with personal data and credentials are not automatically public repo content. Run a secret check before GitHub push.
- `eval/questions.jsonl` contains 10–15 human-reviewed cases including refused questions; `eval/results.json` holds actual results, time, model IDs/config, limitations. Metrics test code on fixtures; actual evaluation on real deployed/integration service when possible. Never invent percentages, latencies, cost or tests.

## Explainability and progress reporting format

After each increment, respond in this order, compact but complete:

```text
Task: [B4 — Chunker]
Assessment trace: [p1 §2 source-extract/chunk/embed]
Changes: [files and functions + concise purpose]
Flow: [input -> key operations -> output; error path]
Tests: [exact commands, count, passed/failed; distinguish mock/live]
Security/cost: [what changes]
Tradeoff: [reason, alternative, limits]
Walkthrough: [1-2 likely reviewer questions with answers]
Ledger: [PASS/FAIL/BLOCKED; next task]
STOP: [wait for Aditya's confirmation]
```

Don't hide a failed test or edit expected outputs merely to turn a failure green; fix code or explain a requirement correction. Do not promise background progress while waiting. Do not push, deploy or provision without a relevant authorization.

## Definition of final handoff

Only call the system submitted/complete if: live callable ECS endpoint works from fresh client; authorized upload and persisted status complete; PDF evidence/citations verifiably map to source; unsupported question refused; auth/validation/owner controls tested; real evaluation and failures recorded; README/diagram mirror actual deployment and cost; GitHub contains no secrets; and candidate can explain IAM/cross-account inference, chunking/embedding/cosine/rerank, grounding, cost and 500K document limits. If anything remains blocked, prominently state it instead of asserting full success.
