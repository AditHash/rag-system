# Evaluation corpus

`questions.jsonl` is a 15-case draft ground-truth set. Most cases draw on the
tracked `README.md` and `docs/decisions.md` files, which can be uploaded as UTF-8
text by using the `README.txt` and `decisions.txt` upload filenames. One conflict
case uses the clearly labeled synthetic fixtures under `sources/`; these only
exercise detection of contradictory evidence. No private assessment or user
document is included.

Each `evidence_ids` value is a stable logical span key, not a runtime chunk UUID.
`evidence.json` maps each key to its source path, upload filename, and exact text
anchor. Runtime document/chunk IDs are generated during ingestion and therefore
cannot be hard-coded into a reusable question set. For TXT sources, the anchor can
be mapped to the service's stored character offsets.

The cases include direct questions, paraphrases, unsupported questions, and one
deliberately contradictory fixture pair. The expected answers and anchors were
checked against the current files, but this dataset is **not yet
human-reviewed by the candidate**. Review each row before using it to claim
assessment ground truth or to calibrate the evidence threshold. It is not a
representative customer-document benchmark.

No model evaluation results are included here. Fake-provider tests do not count
as measured model accuracy. A real run requires local PostgreSQL, configured
Bedrock model access, and explicit approval for any billable inference.
