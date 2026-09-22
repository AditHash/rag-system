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
