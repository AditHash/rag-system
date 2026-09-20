# A0 repository baseline

Inspected 2026-09-20, before application implementation.

| Item | Observed state |
|---|---|
| Tracked files | Only `README.md`, containing `# rag-system`. |
| Existing untracked user files | `.gitignore`, `AGENTS.md`, `instruct.md`, `plan.md`. Preserved; plan source alignment corrected in A0. |
| Guidance | `AGENTS.md` read in full; `instruct.md` has identical contents. No nested AGENTS.md found. |
| Assessment | `project-information/Aditya_Assessment.pdf`, 39,168 bytes, four pages, read in full using embedded Unicode font maps. |
| Ignore policy | Existing `.gitignore` only ignores `/project-information`. PDF remains local and ignored. Secret exclusions belong to A1; current policy is insufficient for credentials. |
| Application and tests | None. No package, dependency manifest, endpoints, providers, migrations, tests, or evaluation artifacts. |
| Deployment | No Dockerfile, infrastructure definitions, deployment evidence, or callable service URL in repo. |
| Documentation | No `docs/` before A0. Existing plan diagram describes proposed infrastructure only. |
| Local PDF tooling | `pdftotext` and Python PDF libraries unavailable. `python` absent; `python3` available. Used a temporary standard-library inspection script, not application extraction code. |
| AWS account | Ready according to user; not independently inspected. No AWS calls made. |
| Bedrock | Access through separate-account credentials according to user; credential type, owner authorization, billing responsibility, lifetime, region, models, dimensions, quotas, and per-capability access unverified. |

No deployed topology is asserted. A0 adds documentation only. A1 and every later task remain unstarted.

## Open prerequisites

- Before A2 live calls: establish credential type without sharing secrets; confirm account-owner authorization and billing responsibility, model IDs/region, and explicit approval for bounded calls. An ECS task role does not itself establish access to another account.
- Before provisioning: approve concrete region, topology, cost estimate, and cleanup plan. No paid resources authorized by A0.
- Before submission: confirm exact cutoff and repository sharing policy. PDF states five days but supplies no issue date; no deadline or extension inferred.
- Embedding dimensions and durable-worker choice remain unresolved. Do not claim working integrations or durable ingestion.

Potential access uncertainty does not prevent local A1 work after user review. A2 has not been attempted; no failed live probe is implied.
