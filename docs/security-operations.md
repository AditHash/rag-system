# Security and operations review

Review date: 2026-09-25. Scope: the current local backend and repository only.
This review does not establish that AWS resources, network rules, or deployed
logging are secure. The assessment asks for sensible storage access controls,
least-needed IAM roles, and no hardcoded credentials (PDF p3); ECS, S3, and the
specific role layout are the selected architecture, not prescribed services.

## Controls verified locally

| Area | Current behavior and evidence | Boundary |
|---|---|---|
| API authentication | Protected routes require `X-API-Key`; comparison uses `secrets.compare_digest`. Missing server configuration returns 503, and a missing or wrong key returns 401. HTTP tests cover these cases. | One shared key maps to `demo-user`. There is no user identity provider, key rotation workflow, or multi-tenant account model. |
| Upload and question bounds | Ingestion accepts one PDF/TXT, limits the file to 10 MiB and the complete multipart request to 10 MiB + 64 KiB, including chunked requests without `Content-Length`. Chat questions are capped at 4,000 characters; `top_k` is limited to 1–20 and document filters to 100 unique IDs. | No request-rate limit is implemented. Request bounds reduce per-request work but do not prevent repeated requests. |
| Owner scope and status | Retrieval SQL filters by authenticated `owner_id`, `READY`, and embedding model. Status lookup filters by job ID and owner; unknown and other-owner jobs both return 404. Tests cover these predicates and status behavior. | This is application-level scoping for one demo principal. It is not PostgreSQL row-level security, and direct database credentials can bypass the API. |
| Error responses | HTTP validation and unexpected failures use a stable JSON envelope; provider/storage details are not returned in tested API error paths. | A safe response does not prove that every framework, SDK, host, or future CloudWatch logger redacts data. Deployed log policy has not been configured or tested. |
| Liveness | `GET /health` returns only process liveness and makes no cloud calls. | It is not a readiness check and does not prove DB, S3, or Bedrock connectivity. |
| S3 adapter | Object keys use validated owner/document IDs, omit client filenames, set no public ACL, and request AES-256 server-side encryption. Fake-client tests verify request shape. | No bucket has been created or tested. Block Public Access, bucket policy, versioning/lifecycle, encryption policy, and IAM scope remain deployment gates. |
| Secrets and model access | Runtime configuration uses environment variables and boto3's credential chain; `.env` and AWS credential paths are ignored. `.env.example` contains names and empty values only. | No ECS task role or Secrets Manager integration is configured. Never bake credentials into the image; a deployed task needs an approved role/secret delivery plan. |
| Database/network | `DATABASE_URL` is read at runtime. The selected deployment places PostgreSQL on the user's EC2 host, reachable only over the intended private network. | TLS requirements, security-group rules, database user grants, password rotation, backups, and host patching have not been verified. |
| Background work | `202` follows S3/job persistence; extraction/indexing runs in FastAPI `BackgroundTasks`. | Work can stop on process restart, and a job can remain `PROCESSING`. No durable queue, retry service, or stuck-job recovery exists. |

## Operational recommendations before public deployment

1. Put the API behind HTTPS ingress and configure a shared edge rate limit. An
   in-process counter would reset on restart and multiply across Uvicorn workers
   or ECS tasks, so it would give a misleading limit for this runtime.
2. Use a least-privilege ECS task role for only required Bedrock model actions
   and the document bucket prefix. Keep the execution role limited to image
   pulls, log delivery, and explicitly required secret retrieval.
3. Keep S3 Block Public Access enabled, deny insecure transport, enforce the
   approved encryption policy, and scope object access to the application
   prefix. Verify those policies with an approved deployment check.
4. Restrict PostgreSQL ingress to the API task security group and required
   administration path. Use a dedicated database role with only schema/table
   privileges the service needs, and enable TLS where supported by the chosen
   private-network setup.
5. Set log retention and access policy before enabling CloudWatch. Do not log
   API keys, uploaded bytes, extracted text, questions, model prompts, or model
   responses. Add alerting for repeated 401/429/5xx responses and stuck jobs.
6. Decide whether to replace process-local ingestion with SQS and a worker before
   claiming durable `202` processing.

These are deployment actions, not evidence that the controls already exist.
Provisioning or making billed AWS calls requires separate approval.

## Negative-check and secret-review record

- API tests cover missing/wrong/unconfigured keys, malformed and oversized
  inputs, safe error bodies, bounded multipart bodies, cross-owner status
  hiding, and owner-scoped retrieval. Relevant files are
  `backend/tests/test_auth_validation.py`, `backend/tests/test_ingest_route.py`,
  `backend/tests/test_chat_route.py`, `backend/tests/test_retrieval.py`, and
  `backend/tests/test_db_migrations.py`.
- Repository review: `.env`, `.aws/`, credential JSON, PEM, and key files are
  ignored; the assessment PDF is ignored. The tracked `.env.example` has no
  secret values. A regex scan of tracked content found no AWS access-key IDs,
  private-key headers, or nonempty credential assignments. This is a basic
  pattern scan, not proof that arbitrary secrets are absent.
- Not verified: deployed IAM, S3 bucket policy, database network/roles, TLS,
  CloudWatch configuration/retention/access, ingress rate limiting, key
  rotation, and recovery of interrupted background jobs.
