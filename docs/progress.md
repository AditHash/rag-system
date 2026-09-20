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
