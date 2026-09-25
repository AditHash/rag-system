# Project instructions

## Goal

Build a small, readable document Q&A backend that the candidate can explain in a walkthrough. Use LangChain components where they keep the code direct. Do not restore deleted modules or add architecture for scale before the basic flow works.

## Current implementation scope

Work in this order, one reviewable task at a time:

1. Ingestion: accept PDF/TXT, extract text with page metadata, split with LangChain, embed with the configured Bedrock embedding model, and store with LangChain's PostgreSQL/pgvector integration.
2. Retrieval: embed a question with the same model, run similarity search, and return chunk text plus source metadata.
3. Only after review, consider reranking.
4. Answer generation, verified citations, refusal behavior, evaluation, and AWS deployment are later tasks. Never describe them as implemented until they are.

Keep functions small, names clear, and folders few. Do not add custom chunking/vector-search code when a LangChain integration covers the need. Do not add agents, workers, queues, repository layers, or a frontend unless the user asks.

## Safety and costs

- Read the relevant assessment requirements and inspect the current worktree before each task. Preserve user deletions and unrelated changes.
- Do not print, commit, or otherwise expose credentials. Keep model IDs and credentials configurable through `backend/src/config.py` and environment variables.
- Do not provision AWS resources or make live/billable Bedrock calls without explicit approval.
- Local API use may call Bedrock and incur inference charges. Clearly tell the user before recommending a manual call.
- Use PostgreSQL specified by `DATABASE_URL`; deployments may point to PostgreSQL on the user's EC2 host. Never hardcode the database address or password.
- Run tests only when requested for the active task. Report skipped tests honestly.

## Completion and Git

After each completed task, inspect the exact diff and check for secrets/private files, run the validation authorized for that task, and commit and push only the files changed for that task. Never stage unrelated user changes, force-push, or claim a push succeeded without checking the result. Stop for the user's review before starting the next task.

In the task handoff, state what changed, how the flow works, validation actually run, cost/security implications, tradeoffs, remaining gaps, commit/push result, and the next task awaiting approval.
