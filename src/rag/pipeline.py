"""RAG retrieval pipeline"""
from typing import Optional, Dict, Any, List
from src.rag.retriever import get_retriever
from src.observability.logger import get_logger

from src.config import settings

logger = get_logger()


async def retrieve_knowledge(query: str, collection: str = None) -> Optional[Dict[str, Any]]:
    """
    Retrieve relevant knowledge for a query

    Args:
        query: User query
        collection: Knowledge collection to search

    Returns:
        Retrieved knowledge content
    """
    if collection is None:
        collection = settings.qdrant_collection_faq

    logger.info("rag.retrieve.start", query=query[:100], collection=collection)

    retriever = get_retriever()

    # Retrieve from Qdrant
    try:
        results = await retriever.retrieve(query, collection, limit=3)

        if results:
            # Combine top results
            content = "\n\n".join([r.get("content", "") for r in results])
            logger.info("rag.retrieve.complete", num_results=len(results), content_length=len(content), scores=[r.get("score", 0) for r in results])
            return {
                "content": content,
                "sources": [r.get("source", "") for r in results],
                "scores": [r.get("score", 0) for r in results]
            }

        logger.info("rag.retrieve.no_results", query=query[:50])
        return None

    except Exception as e:
        logger.error("rag.retrieve.error", error=str(e), error_type=type(e).__name__)
        raise


async def retrieve_policies(query: str) -> Optional[Dict[str, Any]]:
    """Retrieve policy information"""
    return await retrieve_knowledge(query, collection="policies")