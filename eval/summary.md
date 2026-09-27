# Document Q&A evaluation, 2026-09-27

The [13-question set](questions_v1.jsonl) uses two short, synthetic source files
in `fixtures/`. Nine questions have known answers; four ask for facts absent from
the documents. This keeps the ground truth inspectable and avoids uploading
private documents for the repeatable evaluation.

## Method

`backend/tests/test_live_evaluation.py` calls the real FastAPI routes with two
temporary users. It checks signup, login, input validation, TXT ingestion, one
page of a locally supplied sample PDF when available, S3 storage, search,
user isolation, chat, refusal, and logout. It removes only the temporary users,
their vector rows, and their S3 objects afterward.

For each question, the scorecard checks the response status, required answer
facts, and expected source filenames. A refusal passes only when the status is
`INSUFFICIENT_CONTEXT` and no sources are returned. This is a transparent
heuristic, not a semantic proof: a correct paraphrase can fail a phrase check,
and a phrase match can appear in an otherwise poor answer. We also read the
returned answers and source references manually.

## Result

| Measure | Result |
| --- | ---: |
| Answerable questions with expected facts and sources | 9/9 |
| Unanswerable questions correctly refused | 2/4 |
| Overall | 11/13 |
| Cross-user document-ID search and chat | Both returned no other-user content |

| Case | Expected | Observed |
| --- | --- | --- |
| q01–q09 | Answer with the recorded fact and source | All passed |
| q10 | Refuse unknown security budget | Passed |
| q11 | Refuse unknown backup city | Failed: answer said the city was unknown but API marked it `ANSWERED` because it included a citation and did not equal the exact refusal marker |
| q12 | Refuse unknown chief executive | Passed |
| q13 | Refuse unknown airline cabin class | Failed: API returned `UNVERIFIED_ANSWER` rather than `INSUFFICIENT_CONTEXT` |

The two failures are refusal-classification problems, not evidence that the
model invented a city or cabin class in this run. They show why an exact
`INSUFFICIENT_CONTEXT` string check is fragile. The next reviewed change should
make refusal detection explicit and rerun this same set.

## Repeat the check

From `backend/`, with `DATABASE_URL`, `S3_BUCKET`, and AWS credentials configured:

```bash
uv run pytest -q tests/test_live_evaluation.py
RUN_LIVE=1 EVAL_SMOKE=1 uv run pytest -q -s tests/test_live_evaluation.py
RUN_LIVE=1 uv run pytest -q -s tests/test_live_evaluation.py
```

The first command validates the question set offline and skips live calls. The
second runs two representative questions; the third runs all 13. Live runs
write ignored local `eval/results_smoke.json` or `eval/results_v1.json` files
for detailed review. They call S3 and Bedrock and can incur charges. The sample
PDFs are optional and ignored by Git; when present, the check uploads only the
first page of one PDF to limit embedding calls.

RAGAS could add a model-judged faithfulness score without LangSmith, but it is
not part of these results. Versions 0.4.3 and 0.3.9 failed to import alongside
the project's installed LangChain Community package, so no RAGAS score is
claimed. A compatible, isolated evaluator can be tried later; it would make
additional judge-model calls and should complement the ground-truth and refusal
counts above.
