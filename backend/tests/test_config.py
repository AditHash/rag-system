"""Configuration defaults and environment overrides."""

import os
from importlib import reload
from unittest.mock import patch

from src import config


def test_model_ids_can_be_overridden_by_environment() -> None:
    with patch.dict(
        os.environ,
        {
            "BEDROCK_EMBEDDING_MODEL_ID": "embedding-test",
            "BEDROCK_CHAT_MODEL_ID": "chat-test",
            "BEDROCK_THINKING_MODEL_ID": "thinking-test",
            "BEDROCK_RERANKER_MODEL_ID": "reranker-test",
            "BEDROCK_RERANKER_REGION": "reranker-region-test",
            "EVIDENCE_MIN_COSINE_SIMILARITY": "0.72",
        },
    ):
        reload(config)
        assert config.BEDROCK_EMBEDDING_MODEL_ID == "embedding-test"
        assert config.BEDROCK_CHAT_MODEL_ID == "chat-test"
        assert config.BEDROCK_THINKING_MODEL_ID == "thinking-test"
        assert config.BEDROCK_RERANKER_MODEL_ID == "reranker-test"
        assert config.BEDROCK_RERANKER_REGION == "reranker-region-test"
        assert config.EVIDENCE_MIN_COSINE_SIMILARITY == 0.72

    reload(config)
