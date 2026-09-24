"""Bedrock reranking tests use fake clients and never call AWS."""

from uuid import uuid4

import pytest
from botocore.exceptions import ClientError

from src.reranking import (
    BedrockReranker,
    RerankerError,
    RerankerMatch,
    clamp_rerank_top_k,
    rerank_candidates,
)
from src.retrieval import RetrievalCandidate


class FakeBedrockRerankClient:
    def __init__(self, response=None, error: Exception | None = None) -> None:
        self.response = response or {"results": []}
        self.error = error
        self.calls: list[dict[str, object]] = []

    def rerank(self, **kwargs: object):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.response


class FakeReranker:
    model_id = "reranker-test"

    def __init__(self, matches: list[RerankerMatch] | None = None, fail: bool = False) -> None:
        self.matches = matches or []
        self.fail = fail
        self.calls: list[tuple[str, int]] = []

    def rerank(self, query, candidates, number_of_results):
        self.calls.append((query, number_of_results))
        if self.fail:
            raise RerankerError("safe provider failure")
        return self.matches


def _candidates() -> list[RetrievalCandidate]:
    return [
        RetrievalCandidate(
            chunk_id=uuid4(),
            document_id=uuid4(),
            original_filename=f"source-{index}.txt",
            page_number=index + 1,
            ordinal=index,
            content=f"candidate text {index}",
            cosine_distance=0.1 * index,
            similarity=1.0 - (0.1 * index),
        )
        for index in range(3)
    ]


def test_bedrock_reranker_sends_one_query_and_inline_text_sources() -> None:
    client = FakeBedrockRerankClient(
        {
            "results": [
                {"index": 2, "relevanceScore": 0.91},
                {"index": 0, "relevanceScore": 0.73},
            ]
        }
    )
    reranker = BedrockReranker(
        client=client,
        model_id="cohere.rerank-v3-5:0",
        region_name="us-east-1",
    )
    candidates = _candidates()

    matches = reranker.rerank("the query", candidates, 2)

    assert matches == [RerankerMatch(2, 0.91), RerankerMatch(0, 0.73)]
    request = client.calls[0]
    assert request["queries"] == [{"type": "TEXT", "textQuery": {"text": "the query"}}]
    assert request["sources"] == [
        {
            "type": "INLINE",
            "inlineDocumentSource": {
                "type": "TEXT",
                "textDocument": {"text": candidate.content},
            },
        }
        for candidate in candidates
    ]
    assert request["rerankingConfiguration"] == {
        "type": "BEDROCK_RERANKING_MODEL",
        "bedrockRerankingConfiguration": {
            "modelConfiguration": {
                "modelArn": "arn:aws:bedrock:us-east-1::foundation-model/cohere.rerank-v3-5:0"
            },
            "numberOfResults": 2,
        },
    }


def test_bedrock_reranker_creates_agent_runtime_client_in_reranker_region(monkeypatch) -> None:
    client = FakeBedrockRerankClient()
    calls: list[tuple[str, str, object]] = []

    def make_client(service_name, *, region_name, config):
        calls.append((service_name, region_name, config))
        return client

    monkeypatch.setattr("src.reranking.boto3.client", make_client)

    reranker = BedrockReranker(model_id="reranker-test", region_name="us-east-1")

    assert reranker.client is client
    assert calls[0][0:2] == ("bedrock-agent-runtime", "us-east-1")


def test_rerank_candidates_preserves_model_order_and_named_scores() -> None:
    candidates = _candidates()
    reranker = FakeReranker(
        [RerankerMatch(2, 0.91), RerankerMatch(0, 0.73), RerankerMatch(1, 0.31)]
    )

    outcome = rerank_candidates("the query", candidates, reranker, top_k=3)

    assert outcome.reranked is True
    assert outcome.fallback_reason is None
    assert [item.candidate for item in outcome.candidates] == [
        candidates[2],
        candidates[0],
        candidates[1],
    ]
    assert [item.relevance_score for item in outcome.candidates] == [0.91, 0.73, 0.31]
    assert reranker.calls == [("the query", 3)]


def test_reranking_failure_returns_original_order_without_scores() -> None:
    candidates = _candidates()
    reranker = FakeReranker(fail=True)

    outcome = rerank_candidates("the query", candidates, reranker, top_k=2)

    assert outcome.reranked is False
    assert outcome.fallback_reason == "provider_error"
    assert outcome.model_id == "reranker-test"
    assert [item.candidate for item in outcome.candidates] == candidates[:2]
    assert [item.relevance_score for item in outcome.candidates] == [None, None]


def test_invalid_model_indexes_fall_back_without_inventing_scores() -> None:
    candidates = _candidates()
    reranker = FakeReranker([RerankerMatch(99, 0.9)])

    outcome = rerank_candidates("the query", candidates, reranker, top_k=1)

    assert outcome.reranked is False
    assert [item.candidate for item in outcome.candidates] == candidates[:1]
    assert outcome.candidates[0].relevance_score is None


def test_bedrock_reranker_sanitizes_upstream_failure() -> None:
    client = FakeBedrockRerankClient(
        error=ClientError(
            {"Error": {"Code": "AccessDeniedException", "Message": "private upstream detail"}},
            "Rerank",
        )
    )
    reranker = BedrockReranker(client=client, model_id="model-test", region_name="us-east-1")

    with pytest.raises(RerankerError, match="request failed") as error:
        reranker.rerank("the query", _candidates(), 3)
    assert "private upstream detail" not in str(error.value)


def test_empty_candidates_skip_provider_and_empty_query_fails() -> None:
    reranker = FakeReranker()

    outcome = rerank_candidates("the query", [], reranker)

    assert outcome.candidates == []
    assert outcome.reranked is False
    assert reranker.calls == []
    with pytest.raises(ValueError, match="query must not be empty"):
        rerank_candidates("  ", _candidates(), reranker)


@pytest.mark.parametrize("top_k, expected", [(-2, 1), (0, 1), (4, 4), (100, 20)])
def test_reranker_top_k_is_bounded(top_k: int, expected: int) -> None:
    assert clamp_rerank_top_k(top_k) == expected
