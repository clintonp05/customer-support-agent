"""RAG retrieval pipeline.

Queries both noon_faq (section/rule chunks) and noon_policies (summary/section)
with region-scoped pre-filtering, then merges and deduplicates by parent_id
to avoid sending redundant text to the LLM.
"""
from typing import Optional, Dict, Any, List
from src.rag.retriever import get_retriever
from src.observability.logger import get_logger
from src.config import settings

logger = get_logger()

# Intent → category mapping for payload pre-filtering
_INTENT_CATEGORY_MAP = {
    "refund_request":  "refunds",
    "return_request":  "returns",
    "order_status":    "orders",
    "delivery_tracking": "delivery",
    "warranty_claim":  "warranty",
    "payment_issue":   "payments",
    "product_inquiry": "products",
    "cancel_order":    "orders",
    "change_delivery_address": "delivery",
}


async def retrieve_knowledge(
    query: str,
    collection: str = None,
    intent: str = None,
    region: str = "UAE",
) -> Optional[Dict[str, Any]]:
    """Retrieve relevant knowledge for a query.

    Searches noon_faq (rule-level) and noon_policies (section-level) in parallel,
    merges results, deduplicates by parent, and returns combined context.

    Args:
        query:      User's raw query (E5 prefix added internally)
        collection: Override collection (None = auto-select both)
        intent:     Detected intent — used to filter by category for precision
        region:     UAE | KSA | Egypt — scoped to user's market
    """
    retriever = get_retriever()
    category = _INTENT_CATEGORY_MAP.get(intent) if intent else None

    faq_collection = settings.qdrant_collection_faq if hasattr(settings, "qdrant_collection_faq") else "noon_faq"
    policy_collection = "noon_policies"

    if collection:
        # Single collection override (e.g. from retrieve_policies())
        collections_to_query = [collection]
    else:
        collections_to_query = [faq_collection, policy_collection]

    logger.info("rag.retrieve.start", query=query[:80], region=region,
                intent=intent, category=category, collections=collections_to_query)

    all_results: List[Dict[str, Any]] = []
    try:
        for coll in collections_to_query:
            results = await retriever.retrieve(
                query=query,
                collection=coll,
                limit=4,
                score_threshold=0.35,   # E5-base cosine threshold
                region=region,
                category=category,
                active_only=True,
            )
            all_results.extend(results)
    except Exception as exc:
        logger.error("rag.retrieve.error", error=str(exc))
        return None

    if not all_results:
        logger.info("rag.retrieve.no_results", query=query[:50])
        return None

    # Sort by score descending, deduplicate by parent_id to avoid repetition
    all_results.sort(key=lambda r: r["score"], reverse=True)
    seen_parents: set = set()
    deduped: List[Dict[str, Any]] = []
    for r in all_results:
        parent = r.get("parent_id") or r.get("chunk_id")
        if parent not in seen_parents:
            seen_parents.add(parent)
            deduped.append(r)
        if len(deduped) >= 5:
            break

    content_parts = []
    for r in deduped:
        citation = r.get("citation", "")
        text = r["content"]
        if citation:
            content_parts.append(f"[{citation}]\n{text}")
        else:
            content_parts.append(text)

    content = "\n\n".join(content_parts)

    logger.info("rag.retrieve.complete",
                num_raw=len(all_results),
                num_deduped=len(deduped),
                content_length=len(content),
                scores=[round(r["score"], 3) for r in deduped])

    return {
        "content": content,
        "sources": [r.get("source", "") for r in deduped],
        "citations": [r.get("citation", "") for r in deduped],
        "scores": [r.get("score", 0) for r in deduped],
        "region": region,
    }


async def retrieve_policies(query: str, region: str = "UAE") -> Optional[Dict[str, Any]]:
    """Retrieve from noon_policies only (authoritative rules for escalation/compliance)."""
    return await retrieve_knowledge(query, collection="noon_policies", region=region)
