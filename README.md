# Document Q&A backend

A small FastAPI backend for document ingestion and retrieval-augmented answers.
It uses LangChain for document chunks, Bedrock embeddings and chat models, and
PostgreSQL/pgvector storage and search.

It provides an ingestion route, a search route for inspecting retrieval, and a
chat route that retrieves chunks and uses them to generate a cited answer.
Accounts use JWT bearer tokens; uploaded chunks and retrieval are scoped to the
authenticated user.
A measured evaluation is not implemented yet.

## Requirements

- Python 3.12 and `uv`
- PostgreSQL with the `vector` extension installed
- AWS credentials permitted to invoke the configured Bedrock embedding,
  reranking, and chat models in `us-east-1`
- A database user that can create tables and use the `vector` extension

No AWS resources are provisioned by these instructions. Embedding requests are
billable Bedrock calls.

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
The configured AWS identity needs `s3:PutObject` for the bucket's `users/*` keys
when `S3_BUCKET` is set. The bucket and Bedrock models must use the configured
`AWS_REGION` (currently `us-east-1`).

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
and show cited source passages after signup or login. The indexed-file list only
shows uploads from the current browser session; the backend database can hold
older documents belonging to the same account.
The latest upload is selected as the chat source automatically. The source
selector can switch to another upload from this session or search all documents
in the database. Session upload names and IDs are kept in browser session storage
so a refresh does not require re-uploading; file contents are not stored there.
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
splits text into 1,000-character chunks with 150 characters of overlap by
default, embeds the chunks, and stores them in PostgreSQL. If `S3_BUCKET` is set,
the original file is first stored at
`users/<user_id>/documents/<document_id>/original.pdf` (or `.txt`). The key uses
server-generated IDs, not an untrusted filename; it is saved in chunk metadata.
The object is private and explicitly uses SSE-S3 encryption.

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
storage fails after S3 succeeds, the original remains in S3 for recovery; the
current demo has no cleanup or retry job.

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

This is a first grounding layer, not a guarantee against unsupported claims:
the prompt requests document-only answers, and the API checks that references
map to retrieved chunks. It does not yet verify that each claim is supported by
its cited text or use a tested relevance threshold.

## Choices and limits

- `RecursiveCharacterTextSplitter` fits the mixed PDF and plain-text inputs:
  it tries paragraph, line, and word boundaries before cutting at the character
  limit, and `split_documents` keeps each page's source metadata. The default
  1,000-character size and 150-character overlap are simple demo settings, not
  measured optimal values. A heading-based splitter is less useful when PDF
  extraction loses heading structure; a token splitter would control prompt
  length more precisely, but does not by itself preserve natural boundaries.
  Smaller chunks can pinpoint evidence but lose context; larger chunks create
  fewer embeddings yet may dilute retrieval and lengthen answer prompts. For
  large files, the current settings can create many chunks and slow synchronous
  ingestion. We should compare sizes (for example 1,000/150 versus 1,500/200)
  on the evaluation questions before changing the splitter or its settings.
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
  a new document ID; there is no delete endpoint yet. An S3 key prefix separates
  objects by user, while bucket access is controlled by IAM rather than the key
  name itself.
- PDF text extraction does not OCR scanned pages. A file with no extracted
  text is rejected.
- JWTs are stored in browser session storage for this small demo. Use HTTPS
  before exposing the app publicly, since a stolen token grants access until
  expiry or revocation. There is no signup rate limit, password reset, or email
  verification yet.
- There is no measured evaluation set or cloud deployment yet. Reranking
  improves ordering, but does not prove that a chunk answers the question.
  The prompt and citation-ID check are basic safeguards; there is no tested
  relevance threshold or claim-by-claim evidence verification yet.

## Manual checks

Manually ingest a small, non-sensitive text/PDF file, then call
`/api/v1/search` to inspect the
retrieved chunks or `/api/v1/chat` to ask for an answer. Ingestion and search
call the embedding model. Chat calls the embedding model, Cohere reranker, and
one chat model, so these requests may incur charges.
