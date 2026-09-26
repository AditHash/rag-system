"""Create the LangChain PostgreSQL vector store and run similarity search."""

from functools import lru_cache

import boto3
from langchain_aws import BedrockEmbeddings
from langchain_postgres import PGVector

from src import config


@lru_cache(maxsize=1)
def get_vector_store() -> PGVector:
    """Connect LangChain's vector store to the configured local/remote DB."""
    if not config.DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not configured.")

    embeddings = BedrockEmbeddings(
        model_id=config.EMBEDDING_MODEL_ID,
        region_name=config.AWS_REGION,
    )
    return PGVector(
        embeddings=embeddings,
        connection=config.DATABASE_URL,
        collection_name=config.COLLECTION_NAME,
        use_jsonb=True,
    )


def search_documents(
    question: str, top_k: int, user_id: str, document_id: str | None = None
) -> list[dict[str, object]]:
    """Return only this user's closest stored chunks."""
    metadata_filter = {"user_id": user_id}
    if document_id:
        metadata_filter["document_id"] = document_id
    matches = get_vector_store().similarity_search_with_score(
        question, k=top_k, filter=metadata_filter
    )

    return [
        {
            "text": document.page_content,
            "source": document.metadata.get("source", "unknown"),
            "page": document.metadata.get("page"),
            "document_id": document.metadata.get("document_id"),
            "chunk_index": document.metadata.get("chunk_index"),
            "distance": distance,
        }
        for document, distance in matches
    ]


def rerank_documents(question: str, chunks: list[dict[str, object]]) -> list[dict[str, object]]:
    """Order retrieved chunks by Cohere's Bedrock relevance score."""
    if not chunks:
        return []

    client = boto3.client("bedrock-agent-runtime", region_name=config.AWS_REGION)
    response = client.rerank(
        queries=[{"type": "TEXT", "textQuery": {"text": question}}],
        sources=[
            {
                "type": "INLINE",
                "inlineDocumentSource": {
                    "type": "TEXT",
                    "textDocument": {"text": str(chunk["text"])},
                },
            }
            for chunk in chunks
        ],
        rerankingConfiguration={
            "type": "BEDROCK_RERANKING_MODEL",
            "bedrockRerankingConfiguration": {
                "modelConfiguration": {
                    "modelArn": (
                        f"arn:aws:bedrock:{config.AWS_REGION}::foundation-model/"
                        f"{config.RERANK_MODEL_ID}"
                    )
                },
                "numberOfResults": len(chunks),
            },
        },
    )

    return [
        {**chunks[result["index"]], "rerank_score": result["relevanceScore"]}
        for result in sorted(
            response["results"], key=lambda result: result["relevanceScore"], reverse=True
        )
    ]
