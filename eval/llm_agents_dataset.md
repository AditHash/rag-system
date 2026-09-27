# Evaluation set: LLM trace-tampering paper

`questions_llm_agents.jsonl` is a 13-question ground-truth set based on the PDF
in `sample-pdfs/LLM Agents Can Easily Tamper With Their Own Traces -
2609.30266v1.pdf`. It contains nine questions answerable from the paper and four
questions about details the paper does not report. `expected_pages` refers to
physical PDF page numbers, matching the page metadata added during ingestion.

The questions cover the paper's research question, direct tampering tests,
reward and peer experiments, cited spoofing result, and proposed mitigation.
The unanswerable questions check whether the chatbot refuses to invent costs,
timing statistics, or trace-volume totals absent from the paper.

This is a dataset, not a measured result. No live evaluation has been run
against the deployed RAG API for this corpus yet. A live run requires uploading
the PDF and making embedding, reranking, and chat requests through AWS Bedrock;
those calls can incur charges. Keep the existing `questions_v1.jsonl` and its
11/13 baseline separate so results from the two corpora remain comparable only
when clearly labeled.
