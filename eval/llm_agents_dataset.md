# Evaluation: LLM trace-tampering paper

## Dataset

[`questions_llm_agents.jsonl`](questions_llm_agents.jsonl) contains 13 questions
about the sample paper in `sample-pdfs/`: nine answerable questions and four
questions whose answers are not reported. The set covers direct trace-tampering
experiments, reward and peer-workspace findings, the proposed interception
service, and refusal behavior. Expected page numbers are physical PDF pages.
The paper-grounded answer for Q04 is that Muse Spark, running in the Muse Code
harness, was blocked from deleting its traces on every attempt.

## Live evaluation and chunk comparison

On 2026-09-27, the unchanged 13-question set was run against
`https://rag-demo.cwmgenai.com` using the same image, models, reranking, score
floor (`0.15`), and grounding check. Each run used a fresh temporary account,
uploaded the same paper, scoped chat to that document with `top_k=5`, and
deleted the uploaded document and revoked the token afterward. The temporary
account rows remain because there is no account-deletion endpoint.

| Chunk size / overlap | Chunks | Total | Answerable | Strict refusals |
| --- | ---: | ---: | ---: | ---: |
| 1,000 / 150 (comparison baseline) | 140 | 8/13 (61.5%) | 5/9 (55.6%) | 3/4 (75%) |
| 1,000 / 200 (selected demo setting) | 143 | 8/13 (61.5%) | 5/9 (55.6%) | 3/4 (75%) |

The only outcome change was Q11: at 1,000 / 150 the API returned an answer
citing page 10, which failed the refusal check; at 1,000 / 200 it returned
`UNVERIFIED_ANSWER` with no sources. That is a safe abstention, but the strict
metric counts only `INSUFFICIENT_CONTEXT`, so the refusal score remains 3/4.
The 1,000 / 200 setting added three chunks and did not improve the aggregate
score. This small single-document run is directional, not evidence that one
splitter setting is generally better.

The answerable score requires status `ANSWERED`, the expected source and page,
and all required fact groups. An unanswerable question passes the strict
refusal check only when status is `INSUFFICIENT_CONTEXT` and there are no
sources. `UNVERIFIED_ANSWER` is reported separately because it withholds the
draft and returns no sources, but is not counted as the expected refusal state.

## Misses and known limits

The 1,000 / 200 run passed Q03, Q05, Q06, Q08, Q09, Q10, Q12, and Q13. It
missed:

- **Q01, central research question:** weak reranker evidence caused a refusal.
  This avoids the prior run's wrong-page answer, but also rejects an answerable
  question (a false refusal).
- **Q02, mitigation:** the answer omitted the outside-host and append-only
  requirements.
- **Q04, deletion exception:** the cited page was relevant, but the answer
  omitted Muse Spark, the Muse Code harness, and that deletion was blocked on
  every attempt.
- **Q07, peer workspaces:** the answer was incomplete about the models and
  their at-least-90% result.
- **Q11, median time:** the draft had no valid citation, so the API returned
  `UNVERIFIED_ANSWER` rather than the strict insufficient-context response.

This run included a model-based check over cited passages. That verifier used
the same selected chat model as generation, added another billable model call
and latency, and did not prevent all incomplete answers. It has since been
removed. The previous 8/13 result below is historical.

## Live evaluation after retrieval sufficiency check

On 2026-09-28, the same 13 questions were run against the deployed ECS API at
`https://rag-demo.cwmgenai.com` after deploying image `demo-1ccd623` (ECS task
definition revision 8). The run used the selected 1,000 / 200 character chunk
settings, `top_k=5`, the current reranker and its 0.15 score floor, and the new
LLM-based retrieval sufficiency check. A fresh temporary account uploaded the
paper, which produced 143 chunks. The evaluation script requested document
deletion and logout after scoring; temporary account rows remain because the
app has no account-deletion endpoint.

| Measure | Previous live run | Current live run |
| --- | ---: | ---: |
| Overall | 8/13 (61.5%) | 9/13 (69.2%) |
| Answerable with all expected facts and expected source/page | 5/9 (55.6%) | 5/9 (55.6%) |
| Strict refusals | 3/4 (75%) | 4/4 (100%) |
| Indexed chunks | 143 | 143 |

The refusal score improved by one question, while answerable-question
performance did not change. Q01 was a false refusal: it is answerable, but the
retrieval check returned `INSUFFICIENT_CONTEXT`. Q02, Q04, and Q07 were marked
`ANSWERED` with a source on an expected page, but omitted required fact groups.
Q03, Q05, Q06, Q08, and Q09 passed. All four unanswerable questions (Q10–Q13)
were refused with no sources.

This is a small, single-paper scorecard, not proof that hallucinations have
been eliminated. The retrieval check adds an LLM inference call and latency,
and a refusal can be a false negative, as Q01 shows. Reranker scores and the
0.15 cutoff are not calibrated confidence probabilities. The strict expected
fact checks can also mark a correct paraphrase as a failure. RAGAS was not run
and exact Bedrock costs were not captured. Embedding, reranking, evidence-check,
and answer calls may incur charges.

For the walkthrough, Q05 or Q08 is a supported answer; Q10 is a strict refusal;
Q01 demonstrates the retrieval check's false-refusal tradeoff; Q02 or Q07
demonstrates the remaining answer-completeness limitation. Do not describe this
small evaluation as proof that hallucinations are eliminated.
