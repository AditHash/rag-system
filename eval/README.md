# Evaluation corpus

`questions.jsonl` is a 15-case draft ground-truth set. Most cases draw on the
tracked `README.md` and `docs/decisions.md` files. Upload them as UTF-8 text using
the exact `rag-eval-*` filenames listed in `evidence.json`. One conflict case
uses the clearly labeled synthetic fixtures under `sources/`; these only
exercise detection of contradictory evidence. No private assessment or user
document is included.

Each `evidence_ids` value is a stable logical span key, not a runtime chunk UUID.
`evidence.json` maps each key to its source path, unique `rag-eval-*` upload
filename, and exact text anchor. Runtime document/chunk IDs are generated during
ingestion and therefore cannot be hard-coded into a reusable question set. For
TXT sources, the evaluator maps anchors to the stored character offsets.

The cases include direct questions, paraphrases, unsupported questions, and one
deliberately contradictory fixture pair. The expected answers and anchors were
checked against the current files, but this dataset is **not yet
human-reviewed by the candidate**. Review each row before using it to claim
assessment ground truth or to calibrate the evidence threshold. It is not a
representative customer-document benchmark.

## Run it locally

The evaluator uses the same `answer_question` flow as the chat route and reads
retrieval candidates internally for recall measurement; diagnostics are not
added to the public HTTP response. First upload the current README and decision
record plus both conflict fixtures through the authenticated ingest endpoint,
setting each multipart filename to its `upload_filename` in `evidence.json`.
Poll each job until it is
`COMPLETED`. This ingestion writes to S3/PostgreSQL and calls Bedrock embeddings.

Check the corpus without connecting to PostgreSQL or AWS:

```bash
uv run --project backend python scripts/evaluate.py
```

After the four evaluation documents are `READY` for the demo principal, run the
question set and review each answer manually:

```bash
uv run --project backend python scripts/evaluate.py \
  --run --allow-model-calls --manual-review
```

This performs up to 15 query-embedding requests and generation requests for
questions that pass the evidence gate. Adding `--with-reranker` makes extra
reranker requests where evidence is sufficient. To compare runs, select a
separate `--output` path for each; generated `eval/results*.json` files are
ignored by Git because they may contain model responses. No real run is recorded
yet. Bedrock inference and S3 ingestion can incur charges, so do not execute the
live command until those calls are approved. The script records logical adapter
requests, not SDK retry attempts or itemized dollar cost.
