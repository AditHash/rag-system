"""Answer orchestration tests use deterministic providers and candidates."""

from contextlib import contextmanager, nullcontext
from uuid import uuid4

import pytest

from src.answering import (
    UNSUPPORTED_ANSWER,
    UNVERIFIED_ANSWER,
    answer_question,
)
from src.generation import GenerationError, GenerationResult, ParsedAnswer
from src.reranking import RerankerError, RerankerMatch
from src.retrieval import RetrievalCandidate


class FakeEmbeddingProvider:
    model_id = "embedding-test"

    def __init__(self) -> None:
        self.questions: list[str] = []

    def embed_query(self, question: str) -> list[float]:
        self.questions.append(question)
        return [0.0] * 1024


class FakeGenerator:
    def __init__(self, parsed: ParsedAnswer | None = None, error: Exception | None = None) -> None:
        self.parsed = parsed or ParsedAnswer("ANSWERED", "Answer from evidence.", ["S1"])
        self.error = error
        self.calls: list[tuple[str, list[RetrievalCandidate], str]] = []

    def generate(self, question, candidates, model_id):
        self.calls.append((question, list(candidates), model_id))
        if self.error is not None:
            raise self.error
        return GenerationResult(self.parsed, model_id, 10, 5)


class FakeReranker:
    model_id = "reranker-test"

    def __init__(self, indexes: list[int] | None = None, fail: bool = False) -> None:
        self.indexes = indexes or []
        self.fail = fail
        self.calls = 0

    def rerank(self, _query, _candidates, _number_of_results):
        self.calls += 1
        if self.fail:
            raise RerankerError("safe provider failure")
        return [RerankerMatch(index, 0.9 - (index / 10)) for index in self.indexes]


def _candidate(filename: str, similarity: float = 0.9) -> RetrievalCandidate:
    content = f"Evidence from {filename}."
    return RetrievalCandidate(
        chunk_id=uuid4(),
        document_id=uuid4(),
        original_filename=filename,
        page_number=1,
        ordinal=0,
        content=content,
        cosine_distance=1.0 - similarity,
        similarity=similarity,
        start_offset=0,
        end_offset=len(content),
    )


def _connection_factory():
    return nullcontext(object())


def _mock_retrieval(monkeypatch, candidates):
    calls: list[dict[str, object]] = []

    def retrieve(_connection, owner_id, _embedding, model_id, top_k, document_ids):
        calls.append(
            {
                "owner_id": owner_id,
                "model_id": model_id,
                "top_k": top_k,
                "document_ids": document_ids,
            }
        )
        return candidates

    monkeypatch.setattr("src.answering.BEDROCK_EMBEDDING_MODEL_ID", "embedding-test")
    monkeypatch.setattr("src.answering.retrieve_candidates", retrieve)
    return calls


def test_weak_evidence_returns_refusal_without_rerank_or_generation(monkeypatch) -> None:
    _mock_retrieval(monkeypatch, [_candidate("weak.txt", similarity=0.2)])
    embedding = FakeEmbeddingProvider()
    generator = FakeGenerator()
    reranker = FakeReranker([0])

    result = answer_question(
        _connection_factory,
        "  unsupported question  ",
        "owner-a",
        embedding,
        generator,
        reranker,
        min_evidence_similarity=0.55,
    )

    assert result.status == "INSUFFICIENT_CONTEXT"
    assert result.answer == UNSUPPORTED_ANSWER
    assert result.sources == []
    assert result.evidence_reason == "BELOW_THRESHOLD"
    assert embedding.questions == ["unsupported question"]
    assert generator.calls == []
    assert reranker.calls == 0


def test_empty_corpus_returns_refusal_without_generation(monkeypatch) -> None:
    _mock_retrieval(monkeypatch, [])
    generator = FakeGenerator()

    result = answer_question(
        _connection_factory,
        "general knowledge question",
        "owner-a",
        FakeEmbeddingProvider(),
        generator,
    )

    assert result.status == "INSUFFICIENT_CONTEXT"
    assert result.evidence_reason == "NO_CANDIDATES"
    assert result.sources == []
    assert generator.calls == []


def test_answer_flow_reranks_and_binds_sources_to_post_rerank_order(monkeypatch) -> None:
    first = _candidate("first.txt")
    second = _candidate("second.txt", similarity=0.8)
    _mock_retrieval(monkeypatch, [first, second])
    generator = FakeGenerator(ParsedAnswer("ANSWERED", "Grounded.", ["S1"]))
    reranker = FakeReranker([1, 0])

    result = answer_question(
        _connection_factory,
        "What do the documents say?",
        "owner-a",
        FakeEmbeddingProvider(),
        generator,
        reranker,
        top_k=7,
        min_evidence_similarity=0.55,
    )

    assert result.status == "ANSWERED"
    assert result.reranker_used is True
    assert result.generation_model_id == "qwen.qwen3-32b-v1:0"
    assert generator.calls[0][1] == [second, first]
    assert result.sources[0].filename == "second.txt"
    assert result.sources[0].page_number == 1
    assert result.retrieved_candidate_count == 2


def test_thinking_mode_selects_gpt_oss_without_exposing_reasoning(monkeypatch) -> None:
    candidate = _candidate("source.txt")
    _mock_retrieval(monkeypatch, [candidate])
    generator = FakeGenerator()
    monkeypatch.setattr("src.answering.BEDROCK_THINKING_MODEL_ID", "gpt-oss-test")

    result = answer_question(
        _connection_factory,
        "Compare these two policies.",
        "owner-a",
        FakeEmbeddingProvider(),
        generator,
        thinking_mode=True,
    )

    assert result.generation_model_id == "gpt-oss-test"
    assert generator.calls[0][2] == "gpt-oss-test"
    assert "reasoning" not in result.answer.lower()


def test_reranker_failure_uses_original_order_and_continues(monkeypatch) -> None:
    first = _candidate("first.txt")
    second = _candidate("second.txt", similarity=0.8)
    _mock_retrieval(monkeypatch, [first, second])
    generator = FakeGenerator()
    reranker = FakeReranker(fail=True)

    result = answer_question(
        _connection_factory,
        "question",
        "owner-a",
        FakeEmbeddingProvider(),
        generator,
        reranker,
    )

    assert result.status == "ANSWERED"
    assert result.reranker_used is False
    assert generator.calls[0][1] == [first, second]


def test_invalid_model_citations_become_safe_refusal(monkeypatch) -> None:
    _mock_retrieval(monkeypatch, [_candidate("source.txt")])
    generator = FakeGenerator(ParsedAnswer("ANSWERED", "Unsupported answer.", ["S999"]))

    result = answer_question(
        _connection_factory,
        "question",
        "owner-a",
        FakeEmbeddingProvider(),
        generator,
    )

    assert result.status == "INSUFFICIENT_CONTEXT"
    assert result.answer == UNVERIFIED_ANSWER
    assert result.sources == []
    assert result.evidence_reason == "INVALID_CITATIONS"


def test_generator_errors_propagate_for_service_layer_mapping(monkeypatch) -> None:
    _mock_retrieval(monkeypatch, [_candidate("source.txt")])
    generator = FakeGenerator(error=GenerationError("Bedrock answer generation failed"))

    with pytest.raises(GenerationError, match="generation failed"):
        answer_question(
            _connection_factory,
            "question",
            "owner-a",
            FakeEmbeddingProvider(),
            generator,
        )


def test_db_connection_is_open_only_for_retrieval(monkeypatch) -> None:
    events: list[str] = []
    candidate = _candidate("source.txt")

    def embed(_question, _provider, _model_id):
        events.append("embed")
        return [0.0] * 1024

    def retrieve(_connection, *_args, **_kwargs):
        events.append("retrieve")
        return [candidate]

    @contextmanager
    def connection_factory():
        events.append("db_open")
        yield object()
        events.append("db_close")

    class OrderedGenerator(FakeGenerator):
        def generate(self, question, candidates, model_id):
            events.append("generate")
            return super().generate(question, candidates, model_id)

    monkeypatch.setattr("src.answering.BEDROCK_EMBEDDING_MODEL_ID", "embedding-test")
    monkeypatch.setattr("src.answering.embed_query", embed)
    monkeypatch.setattr("src.answering.retrieve_candidates", retrieve)

    answer_question(
        connection_factory,
        "question",
        "owner-a",
        FakeEmbeddingProvider(),
        OrderedGenerator(),
    )

    assert events == ["embed", "db_open", "retrieve", "db_close", "generate"]
