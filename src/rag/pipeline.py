"""RAG retrieval pipeline"""
from typing import Optional, Dict, Any, List
from src.rag.retriever import get_retriever


async def retrieve_knowledge(query: str, collection: str = "faq") -> Optional[Dict[str, Any]]:
    """
    Retrieve relevant knowledge for a query

    Args:
        query: User query
        collection: Knowledge collection to search

    Returns:
        Retrieved knowledge content
    """
    retriever = get_retriever()

    # Retrieve from Qdrant
    results = await retriever.retrieve(query, collection, limit=3)

    if results:
        # Combine top results
        content = "\n\n".join([r.get("content", "") for r in results])
        return {
            "content": content,
            "sources": [r.get("source", "") for r in results],
            "scores": [r.get("score", 0) for r in results]
        }

    return None


async def retrieve_policies(query: str) -> Optional[Dict[str, Any]]:
    """Retrieve policy information"""
    return await retrieve_knowledge(query, collection="policies")