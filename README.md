# Document Q&A backend

A small FastAPI backend for document ingestion and retrieval-augmented answers.
It uses LangChain for document chunks, Bedrock embeddings and chat models, and
PostgreSQL/pgvector storage and search.

It provides an ingestion route, a search route for inspecting retrieval, and a
chat route that retrieves chunks and uses them to generate a cited answer.
Accounts use JWT bearer tokens; uploaded chunks and retrieval are scoped to the
authenticated user.
The paper-specific [evaluation set and measured results](eval/llm_agents_dataset.md)
cover answerable questions and refusal behavior. The previous synthetic-corpus
baseline is documented separately in [eval/summary.md](eval/summary.md).

## Assessment deliverables

- **Working demo:** the deployed backend and interactive API docs are available
  at [`rag-demo.cwmgenai.com/docs`](https://rag-demo.cwmgenai.com/docs). The
  frontend is provided for local use and is not hosted.
- **Source and walkthrough notes:** this README describes how to run the app,
  its ingestion and retrieval flow, chunking and reranking choices, grounding
  limits, and AWS deployment.
- **Evaluation:** the 13-question paper-specific set and measured results are
  in [`questions_llm_agents.jsonl`](eval/questions_llm_agents.jsonl) and
  [`llm_agents_dataset.md`](eval/llm_agents_dataset.md). The latest live run
  scored 8/13 at the selected 1,000 / 200 chunk settings; see the report for
  misses and the comparison with 1,000 / 150.
- **Architecture:** the flow and architecture diagram is
  [`rag.drawio.svg`](rag.drawio.svg); [`deployment/`](deployment/README.md)
  contains the deployment guide and detailed AWS infrastructure diagram.
- **Deployment artifacts:** task definition and least-privilege IAM policy
  examples are documented in [`deployment/README.md`](deployment/README.md).

## Requirements

- Python 3.12 and `uv`
- PostgreSQL with the `vector` extension installed
- AWS credentials permitted to invoke the configured Bedrock embedding,
  reranking, and chat models in `us-east-1`
- A database user that can create tables and use the `vector` extension

No AWS resources are provisioned by these instructions. Embedding requests are
billable Bedrock calls.

## Run the full demo locally

The backend needs PostgreSQL/pgvector, a configured `backend/.env`, and AWS
credentials with permission to call the configured Bedrock models. Start it in
one terminal:

```bash
cd backend
cp .env.example .env
# Edit .env with your database URL and a private JWT_SECRET.
uv sync --frozen
uv run main.py
```

In a second terminal, start the frontend:

```bash
cd frontend
npm install
npm run dev
```

Open `http://127.0.0.1:5173`. Its development server forwards API requests to
the backend at `http://127.0.0.1:8000`. The backend is the hosted deliverable;
the frontend is only provided for a local walkthrough. Uploading or asking a
question can make billable Bedrock requests.

## Configure and run

From `backend/`, copy `.env.example` to `.env` and fill in the database URL and
`JWT_SECRET`. Set `S3_BUCKET` to an existing private bucket to keep original
uploads; leave it empty for a local vector-only run. Generate the secret locally with
`python -c 'import secrets; print(secrets.token_urlsafe(48))'` and paste it into
`.env`; keep that file private. The backend creates `app_users` and
`revoked_tokens` tables on startup. A missing or short JWT secret stops startup.
The app loads settings from that file when it starts.
Use your normal AWS credential chain (for example, `AWS_PROFILE`) for Bedrock
access; AWS credentials themselves are not loaded from this file by the app.

```bash
cd backend
cp .env.example .env
# Edit .env; do not commit it.
uv sync --frozen
uv run main.py
```

The database URL uses the psycopg 3 SQLAlchemy scheme, for example:

```text
postgresql+psycopg://user:password@localhost:5432/document_db
```

The LangChain vector store creates its own tables in the configured database.
The PostgreSQL server must already have pgvector installed. Model IDs, region,
chunk size, overlap, collection name, S3 bucket, and database URL are configurable
in `backend/src/config.py` through environment variables. `AWS_PROFILE` is read
by the standard AWS credential chain and does not need to be copied into code.
The configured AWS identity needs `s3:PutObject` and `s3:DeleteObject` for the
bucket's `users/*` keys when `S3_BUCKET` is set. The bucket and Bedrock models
must use the configured `AWS_REGION` (currently `us-east-1`).

Check the process health and interactive API documentation:

```bash
curl http://127.0.0.1:8000/health
# {"status":"ok"}
```

Open `http://127.0.0.1:8000/docs` to explore the endpoints.

## Run the frontend

The small browser interface lives in `frontend/`. With the backend running in
another terminal, start it with Node.js 18 or newer:

```bash
cd frontend
npm install
npm run dev
```

Open `http://127.0.0.1:5173`. The development server forwards `/api` and
`/health` requests to the local backend, so no CORS setting is needed. The
frontend can upload PDF/TXT files, ask questions in normal or thinking mode,
and show cited source passages after signup or login. The indexed-file list
loads the account's document records from PostgreSQL, including files uploaded
in earlier sessions. The latest upload is selected as the chat source
automatically. The source selector can switch to another upload or search all
documents in the database. The list also lets the owner delete a document.
The JWT is also held in browser session storage and is cleared on logout.
`npm run build` creates static files in `frontend/dist/`. In deployment, serve
those files and route `/api` and `/health` to FastAPI on the same origin.
Uploading and asking questions invoke Bedrock models and may incur charges.

## Accounts and access

Create an account or log in through the frontend, or use these API routes:

- `POST /api/v1/signup` with `{"username":"alice","password":"your-password"}`
  creates a user and returns an access token.
- `POST /api/v1/login` with the same fields returns an access token.
- `GET /api/v1/me` returns the current user.
- `POST /api/v1/logout` revokes the current token (HTTP 204). Log in again for a
  new token.

Usernames are case-insensitive and must be 3–32 letters, digits, or underscores.
Passwords must be 8–128 characters and are stored as Argon2 hashes. The JWT
expires after `JWT_EXPIRE_MINUTES` (12 hours by default). Send it as
`Authorization: Bearer <token>` to `/me`, `/logout`, `/ingest`, `/search`, and
`/chat`. For example, after copying the token into your shell:

```bash
export RAG_TOKEN='paste-token-here'
curl -H "Authorization: Bearer $RAG_TOKEN" http://127.0.0.1:8000/api/v1/me
```

The API derives the user ID from the signed token and verifies that the user
still exists. Ingestion tags chunks with that ID, and both search and chat filter
pgvector results by it. A `document_id` narrows results only within that user's
documents; it cannot select another user's file. Chat history is held in the
browser only, so logging out or refreshing clears the visible conversation.
Chunks indexed before this change have no user ID and are intentionally invisible
to all accounts; re-upload those files while logged in.

## Ingest a document

PDF and UTF-8 TXT files up to 10 MiB are accepted. The endpoint extracts text,
keeps the source filename and 1-based page in LangChain document metadata,
splits text into 1,000-character chunks with 200 characters of overlap by
default, embeds the chunks, and stores them in PostgreSQL. If `S3_BUCKET` is set,
the original file is first stored at
`users/<user_id>/documents/<document_id>/original.pdf` (or `.txt`). The key uses
server-generated IDs, not an untrusted filename.
The object is private and explicitly uses SSE-S3 encryption. A separate
`uploaded_documents` row stores the original filename, owner, S3 bucket and key,
chunk count, status, and upload time once per document.

```bash
curl --fail --show-error \
  -H "Authorization: Bearer $RAG_TOKEN" \
  -F 'file=@./example.pdf' \
  http://127.0.0.1:8000/api/v1/ingest
```

Example response:

```json
{
  "document_id": "2e7a...",
  "source": "example.pdf",
  "status": "indexed",
  "chunk_count": 8
}
```

Ingestion is synchronous in this demo. It returns only after the optional S3
write, Bedrock embeddings, and PostgreSQL writes finish. If embedding or database
storage fails, the backend tries to remove the partial chunks and S3 object.
Cleanup is best effort because PostgreSQL and S3 do not share a transaction.

`GET /api/v1/documents` lists the signed-in user's records, including their S3
locations. `DELETE /api/v1/documents/{document_id}` removes an owned document,
its vector chunks, and its original S3 object. Existing LangChain chunks are
backfilled into the document list when the backend starts; their S3 bucket is
assumed to match the current `S3_BUCKET` setting.

## Search stored documents

```bash
curl --fail --show-error \
  -H "Authorization: Bearer $RAG_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"question":"What does the document say about retention?","top_k":5}' \
  http://127.0.0.1:8000/api/v1/search
```

Each result includes the chunk text, filename, page, document ID, chunk index,
and pgvector distance. Smaller distance means a closer vector match; this is a
retrieval diagnostic, not a calibrated answer-confidence score.

## Ask a question and get an answer

The chat route calls the same retrieval function directly; it does not make an
HTTP request to `/api/v1/search`. It takes up to five pgvector matches, sends
their text to Cohere Rerank 3.5 through Bedrock in `us-east-1`, and presents
them to the answer model in reranked order. Five limits reranking cost and the
amount of text in the answer prompt. Qwen3 32B answers by default; set
`thinking_mode` to `true` to select GPT-OSS 20B. All Bedrock models use the
same `AWS_REGION` setting, which defaults to `us-east-1`.
An optional `document_id` scopes search and chat to one uploaded document;
without it, both endpoints search all documents owned by the current user.

```bash
curl --fail --show-error \
  -H "Authorization: Bearer $RAG_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"question":"How long are records kept?","top_k":5,"thinking_mode":false}' \
  http://127.0.0.1:8000/api/v1/chat
```

An answered response includes an answer with numbered references such as `[1]`
and source chunks whose `source_id` matches those references. If there are no
retrieved chunks, or the model refuses or omits a valid reference, the endpoint
returns `INSUFFICIENT_CONTEXT` with an empty `sources` list. References are
numbered after reranking, so each reference points to the chunk shown in the
response. Each cited source also has a `rerank_score` for inspection; it is not
an answer-confidence score.
If the model returns text without a valid citation, the API returns
`UNVERIFIED_ANSWER` instead of incorrectly claiming that the documents lack
the answer. It does not display that uncited text as a grounded answer.

Example response:

```json
{
  "status": "ANSWERED",
  "answer": "The records are kept for 30 days [1].",
  "sources": [
    {
      "source_id": 1,
      "source": "retention-policy.pdf",
      "page": 2,
      "text": "Records are kept for 30 days...",
      "rerank_score": 0.91
    }
  ]
}
```

The API refuses before generation when the top Cohere rerank score is below
`MIN_RERANK_SCORE` (default `0.15`) and checks that answer references map to
retrieved chunks. The answer prompt asks the model to respond only when the
passages directly support every requested detail, and to refuse when details
are missing or unclear. Answers without valid citations are withheld as
`UNVERIFIED_ANSWER`. There is no second model-based answer-verification call:
that call added latency and cost, and used the same model as the generator.
Prompt instructions and citation-ID checks do not prove that the claims are
semantically supported, so the system can still hallucinate or give incomplete
answers.

LangChain's existing `ChatBedrockConverse` supports attaching a configured
Bedrock Guardrail through `guardrail_config`, so no extra Python dependency is
needed. It still requires creating a Guardrail in AWS and incurs filter usage
charges. More importantly, AWS currently documents its contextual-grounding
check as unsupported for conversational QA/chatbot use cases, so this demo
does not enable it. See the [LangChain parameter](https://reference.langchain.com/python/langchain-aws/chat_models/bedrock_converse/ChatBedrockConverse/guardrail_config),
[AWS contextual grounding documentation](https://docs.aws.amazon.com/bedrock/latest/userguide/guardrails-contextual-grounding-check.html),
and [Bedrock pricing](https://aws.amazon.com/bedrock/pricing/).

## Choices and limits

- `RecursiveCharacterTextSplitter` fits the mixed PDF and plain-text inputs:
  it tries paragraph, line, and word boundaries before cutting at the character
  limit, and `split_documents` keeps each page's source metadata. The default
  1,000-character size and 200-character overlap are simple demo settings, not
  measured optimal values. On the current 13-question set, 1,000 / 150 and
  1,000 / 200 each scored 8/13; 1,000 / 200 produced 143 chunks versus 140
  and changed Q11 from an `ANSWERED` response citing page 10 to
  `UNVERIFIED_ANSWER` with no sources. The score was unchanged, so this small
  run is directional only. A heading-based
  splitter is less useful when PDF extraction loses heading structure; a token
  splitter would control prompt length more precisely, but does not by itself
  preserve natural boundaries.
  Smaller chunks can pinpoint evidence but lose context; larger chunks create
  fewer embeddings yet may dilute retrieval and lengthen answer prompts. For
  large files, the current settings can create many chunks and slow synchronous
  ingestion.
- Amazon Titan Text Embeddings V2 is the default embedding model. The same
  configured embedding object/model is used for document and query vectors.
- Qwen3 32B (`BEDROCK_CHAT_MODEL_ID`) is used for normal answers; GPT-OSS 20B
  (`BEDROCK_THINKING_MODEL_ID`) is selected by `thinking_mode=true`.
- LangChain's PostgreSQL vector store keeps vector persistence and similarity
  search in PostgreSQL, which is already part of the planned local setup.
- Bedrock's Rerank API orders the pgvector candidates by how directly they
  relate to the question. The installed LangChain AWS package has no direct
  reranker integration, so this one call uses Boto3. `/search` still shows raw
  pgvector results to make the first retrieval stage easy to inspect.
- Raw files are saved to S3 only when `S3_BUCKET` is configured. A new upload gets
  a new document ID. An S3 key prefix separates
  objects by user, while bucket access is controlled by IAM rather than the key
  name itself.
- PDF text extraction does not OCR scanned pages. A file with no extracted
  text is rejected.
- JWTs are stored in browser session storage for this small demo. Use HTTPS
  before exposing the app publicly, since a stolen token grants access until
  expiry or revocation. There is no signup rate limit, password reset, or email
  verification yet.
- The latest paper-specific evaluation scored 8/13 (5/9 answerable; 3/4
  strict refusals, with the remaining unanswerable question receiving an
  unverified response without sources). That run used the now-removed extra
  model verification call, so its results are historical and should be rerun
  before describing current behavior. See the [evaluation report](eval/llm_agents_dataset.md).
  Reranking, a score floor, prompt instructions, and citation-ID checks reduce
  risk but do not prove every answer is grounded.

## AWS demo deployment

The API is deployed in `us-east-1` in the account's default VPC. Open
[`https://rag-demo.cwmgenai.com/docs`](https://rag-demo.cwmgenai.com/docs) for
the interactive API documentation; [`/health`](https://rag-demo.cwmgenai.com/health)
checks that the service is responding. The frontend is not hosted by this
deployment.

An HTTPS Application Load Balancer forwards requests to one small Fargate task.
The task uses a public IP for outbound access to ECR, S3, and Bedrock, while its
security group accepts application traffic only from the load balancer. HTTP
redirects to HTTPS. The task uses the `document-qa-task` role for the configured
Bedrock models and only `PutObject`/`DeleteObject` under the bucket's
`users/*` prefix. A separate `document-qa-execution` role can pull the single
ECR repository, read the runtime secret, and write to the API log group.

PostgreSQL 16 with pgvector runs on the existing `t3a.micro` EC2 instance in the
same VPC. The application database URL and JWT signing key are held in the
`document-qa/runtime` Secrets Manager secret and injected when the task starts;
no static AWS credentials are stored in the container. PostgreSQL port 5432 is
allowed only from the API task security group. The instance has a public IP
because it was created in a default public subnet, but its security group does
not allow internet access to PostgreSQL; SSH is restricted to the operator's
current public IP. This is network-filtered access, not a private-subnet setup.

The previous database was moved from `ap-south-2`, verified, and its old EC2
instance was terminated. Its four vector rows remain in the new database. They
pre-date user ownership metadata, so they are not listed or returned by the
current per-user API; newly ingested documents are scoped to the signed-in user.

The deployment uses one task with 0.25 vCPU and 1 GiB memory, one ALB, one
`t3a.micro` database instance, one Secrets Manager secret, and short-retention
logs. At low traffic, the expected infrastructure charge is roughly USD 4–6
for 72 hours, before any Bedrock inference, substantial data transfer, or
unexpected account-specific charges. This is an estimate, not a spending cap;
check the AWS bill. A one-time shutdown is scheduled for 2026-09-30 12:58 UTC:
it scales the ECS service to zero, stops the database instance, and deletes the
load balancer. The database EBS volume and small storage charges remain so its
data is preserved. AWS bills for Fargate task resources and ALB running time
([Fargate pricing](https://aws.amazon.com/fargate/pricing/),
[ALB pricing](https://aws.amazon.com/elasticloadbalancing/pricing/), and public
IPv4 addresses at the applicable hourly rate
([AWS public IPv4 pricing notice](https://aws.amazon.com/blogs/aws/new-aws-public-ipv4-address-charge-public-ip-insights/)). Ingestion,
search, and chat call Bedrock and can incur additional usage charges; no
Bedrock inference was made as part of deployment. The current deployment guide,
task definition template, IAM policies, and live resource inventory are in
[`deployment/`](deployment/README.md). They document the existing stack and
provide reusable task and role artifacts; they do not recreate the entire VPC,
security groups, database, load balancer, or DNS as infrastructure-as-code.
The flow and architecture overview below is the Draw.io diagram. The
[deployment guide](deployment/README.md) includes a separate detailed AWS
infrastructure diagram with the current VPC, subnet, service, and security layout.

[Open the editable Draw.io SVG](rag.drawio.svg).

![RAG flow and architecture diagram](rag.drawio.svg)

## Manual checks

Manually ingest a small, non-sensitive text/PDF file, then call
`/api/v1/search` to inspect the
retrieved chunks or `/api/v1/chat` to ask for an answer. Ingestion and search
call the embedding model. Chat calls the embedding model, Cohere reranker, and
one chat model, so these requests may incur charges.
