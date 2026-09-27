# Evaluation: LLM trace-tampering paper

## Dataset

[`questions_llm_agents.jsonl`](questions_llm_agents.jsonl) contains 13 questions
about the sample paper in `sample-pdfs/`: nine answerable questions and four
questions whose answers are not reported. The set covers direct trace-tampering
experiments, reward and peer-workspace findings, the proposed interception
service, and refusal behavior. Expected page numbers are physical PDF pages.
The paper-grounded answer for Q04 is that Muse Spark, running in the Muse Code
harness, was blocked from deleting its traces on every attempt.

## Live run

On 2026-09-27, the set was sent to the deployed API at
`https://rag-demo.cwmgenai.com`. The paper was uploaded into a temporary test
account, indexed as 140 chunks, and every chat request was scoped to that
document with `top_k=5`. The live pipeline performed pgvector retrieval,
reranking, and answer generation. After the run, the uploaded document was
deleted and the access token revoked. The temporary account record remains
because there is no account-deletion endpoint.

| Measure | Result |
| --- | ---: |
| Overall | 9/13 (69.2%) |
| Answerable questions | 5/9 (55.6%) |
| Unanswerable questions refused with no sources | 4/4 (100%) |
| Indexed chunks | 140 |

The score requires an `ANSWERED` response, the expected source and page, and
all required fact groups. Alternative wording in Q03 was corrected after
reviewing its answer against page 4; the answer listed all four scenarios but
used valid paraphrases that the original substring checker missed. Refusal
passes only when the API returns `INSUFFICIENT_CONTEXT` and no sources.

## What failed

- **Q01, central research question:** the answer sounded plausible, but its only
  cited passage came from page 14, the paper's references, rather than the
  introduction on page 2. This is a grounding failure, even though the answer
  resembles the actual research question.
- **Q02, mitigation:** the answer mentioned an interception mechanism between
  the harness and model, but omitted that it must be outside the agent host's
  control and use append-only records.
- **Q04, deletion exception:** the answer discussed refusal to fabricate reset
  events and trace recreation after deletion. It did not answer the question
  about Muse Spark and the Muse Code harness.
- **Q07, peer workspaces:** the answer said “most models” where the paper says
  every tested model except Muse Spark. It was therefore incomplete.

Q03 was correct on manual review after allowing the documented paraphrases.
Q05, Q06, Q08, and Q09 passed the fact and citation checks. All four questions
about unreported costs, timing, deleted bytes, and electricity cost were
correctly refused without sources.

## Limits and next steps

This is a small, single-document run. Fact checking is based on expected terms,
source filename, and page, followed by manual review; it is not a semantic
judge and does not prove that every sentence is entailed by a cited chunk. The
Q01 result demonstrates that valid-looking answer text and a citation do not
guarantee grounding. RAGAS was not run, and no exact Bedrock cost was captured.
Bedrock embedding, reranking, and generation requests were made and may incur
charges.

For the walkthrough, show Q05 or Q08 as a supported answer and Q10 as a refusal.
Also show Q01 as a known failure: retrieval cited the wrong page. The next
engineering task should improve evidence sufficiency/citation validation and
then rerun this unchanged set. Do not present this evaluation as proof that the
chatbot cannot hallucinate.
