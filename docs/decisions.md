# Decisions and unresolved choices

Recorded at A0, 2026-09-20. These are selected design directions, not implemented capabilities.

| Decision | Reason and tradeoff | State |
|---|---|---|
| Follow PDF outcomes and plan task order; stop after each task | Keeps increments reviewable and defensible; adds explicit review checkpoints | Active workflow |
| ECS Fargate + FastAPI | User-selected container API; greater control over runtime/worker lifecycle than Lambda, with idle cost and networking overhead | Selected, not built |
| Private S3 + PostgreSQL/pgvector | User-selected split: raw documents in object storage, transactional metadata/vectors in DB; avoids separate vector-store machinery, but DB scaling/indexing require care | Selected; hosting not provisioned |
| Amazon Bedrock through separately authorized account credentials | Matches user access situation; adds auth, ownership and billing boundaries. Credential mechanism must be verified before adapter selection | Integration unverified; A2 approval gate |
| Layered grounding and server-built citations | Meets highest-priority refusal/verifiability requirements; citation existence alone does not prove factual support | Planned, no mechanism implemented |
| SQS worker conditional; reranker/Guardrails optional | Protects core scope and budget. Skipping durable queue requires explicit interruption limitations; optional model calls add cost/latency | Undecided/off until implemented and verified |
| Deterministic local fakes; separately approved live checks | Local testing without inference charges; fake success cannot establish real AWS access or evaluation quality | Planned test policy |

Pending: confirmed deadline, region, authorized credential type/lifetime/billing, generation and embedding models/dimensions/quotas, worker mode, database hosting, ingress and approved budget. No secrets belong in these records.
