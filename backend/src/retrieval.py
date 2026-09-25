"""Create the LangChain PostgreSQL vector store and run similarity search."""

from functools import lru_cache

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


def search_documents(question: str, top_k: int) -> list[dict[str, object]]:
    """Return the closest stored chunks and their source metadata."""
    matches = get_vector_store().similarity_search_with_score(question, k=top_k)

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
