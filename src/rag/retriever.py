"""Qdrant semantic search retriever.

Storage structure recap:
  - Each Qdrant Point = { id, vector (768-d E5), payload (JSON metadata) }
  - Vectors stored in memory-mapped HNSW index per segment
  - Payloads stored in RocksDB alongside vectors
  - Payload indexes (KEYWORD/BOOL/DATETIME) enable O(log n) pre-filtering
    before HNSW traversal — critical for region + is_active filters

Collections:
  noon_faq      — customer-facing Q&A (section + rule level chunks)
  noon_policies — authoritative policy rules (summary + section level)
  noon_intents  — intent utterance examples

Payload indexes created on every collection:
  region, is_active, category, chunk_level, intent_tags, language, version
"""
from typing import List, Dict, Any, Optional
import uuid as _uuid

from qdrant_client import QdrantClient
from qdrant_client.http import models as qm

from src.rag.embedder import get_embedder
from src.config import settings
from src.observability.logger import get_logger

logger = get_logger()

_VECTOR_DIM = 768  # multilingual-e5-base output dimension
_DISTANCE = qm.Distance.COSINE

# Fields that get payload indexes for fast pre-filtering
_KEYWORD_INDEXES = ["region", "category", "chunk_level", "access_level", "language", "version"]
_BOOL_INDEXES = ["is_active", "verified"]
_TEXT_INDEXES = ["intent_tags"]  # keyword array — stored as repeated keyword


class QdrantRetriever:
    """Qdrant-backed semantic retriever with metadata filtering."""

    def __init__(self, client: QdrantClient = None):
        self.client = client or QdrantClient(url=settings.qdrant_url)
        self.embedder = get_embedder()
        self._ensure_collections()

    # ------------------------------------------------------------------
    # Collection & index management
    # ------------------------------------------------------------------

    def _ensure_collections(self):
        collections = ["noon_faq", "noon_policies", "noon_intents"]
        for name in collections:
            self._ensure_collection(name)
            self._ensure_payload_indexes(name)

    def _ensure_collection(self, name: str):
        try:
            info = self.client.get_collection(name)
            existing_dim = info.config.params.vectors.size
            if existing_dim != _VECTOR_DIM:
                logger.warning(
                    "qdrant.dim_mismatch_recreating",
                    collection=name,
                    existing=existing_dim,
                    expected=_VECTOR_DIM,
                )
                self.client.delete_collection(name)
                raise Exception("recreate")
            logger.info("qdrant.collection_ok", collection=name, dim=existing_dim)
        except Exception:
            try:
                self.client.create_collection(
                    collection_name=name,
                    vectors_config=qm.VectorParams(size=_VECTOR_DIM, distance=_DISTANCE),
                    hnsw_config=qm.HnswConfigDiff(m=16, ef_construct=128),
                    optimizers_config=qm.OptimizersConfigDiff(memmap_threshold=20_000),
                )
                logger.info("qdrant.collection_created", collection=name, dim=_VECTOR_DIM)
            except Exception as exc:
                logger.warning("qdrant.collection_create_failed", collection=name, error=str(exc))

    def _ensure_payload_indexes(self, collection: str):
        """Create payload indexes so filtered queries skip linear scan."""
        for field in _KEYWORD_INDEXES:
            self._create_index(collection, field, qm.PayloadSchemaType.KEYWORD)
        for field in _BOOL_INDEXES:
            self._create_index(collection, field, qm.PayloadSchemaType.BOOL)
        for field in _TEXT_INDEXES:
            # intent_tags is a list of strings — index each value as keyword
            self._create_index(collection, field, qm.PayloadSchemaType.KEYWORD)

    def _create_index(self, collection: str, field: str, schema_type):
        try:
            self.client.create_payload_index(
                collection_name=collection,
                field_name=field,
                field_schema=schema_type,
            )
        except Exception:
            pass  # index already exists — Qdrant raises on duplicate

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    async def retrieve(
        self,
        query: str,
        collection: str,
        limit: int = 5,
        score_threshold: float = 0.0,
        region: Optional[str] = None,
        category: Optional[str] = None,
        chunk_level: Optional[str] = None,
        active_only: bool = True,
    ) -> List[Dict[str, Any]]:
        """Retrieve relevant documents with optional payload pre-filters.

        Args:
            query:         User query string (will be prefixed with 'query: ')
            collection:    noon_faq | noon_policies | noon_intents
            limit:         Max results
            score_threshold: Min cosine similarity (0.0 = no threshold)
            region:        Filter to UAE | KSA | Egypt | ALL (None = no filter)
            category:      Filter to returns | refunds | delivery | warranty | payments | orders | products
            chunk_level:   Filter to summary | section | rule
            active_only:   When True, only return chunks where is_active=true
        """
        import time
        start = time.time()

        logger.info("qdrant.retrieve.start", query=query[:60], collection=collection,
                    limit=limit, region=region, category=category, active_only=active_only)

        # Build Qdrant filter conditions
        must_conditions = []
        if active_only:
            must_conditions.append(qm.FieldCondition(key="is_active", match=qm.MatchValue(value=True)))
        if region and region != "ALL":
            # Match explicit region OR "ALL" (region-agnostic chunks)
            must_conditions.append(
                qm.Filter(should=[
                    qm.FieldCondition(key="region", match=qm.MatchValue(value=region)),
                    qm.FieldCondition(key="region", match=qm.MatchValue(value="ALL")),
                ])
            )
        if category:
            must_conditions.append(qm.FieldCondition(key="category", match=qm.MatchValue(value=category)))
        if chunk_level:
            must_conditions.append(qm.FieldCondition(key="chunk_level", match=qm.MatchValue(value=chunk_level)))

        qdrant_filter = qm.Filter(must=must_conditions) if must_conditions else None

        try:
            # Use query-prefixed embedding for retrieval
            query_embedding = await self.embedder.aembed_query([query])
            query_vector = query_embedding[0]

            query_response = self.client.query_points(
                collection_name=collection,
                query=query_vector,
                limit=limit,
                query_filter=qdrant_filter,
                with_payload=True,
                score_threshold=score_threshold,
            )

            points = getattr(query_response, "points", [])
            elapsed_ms = int((time.time() - start) * 1000)

            results = []
            for hit in points:
                payload = hit.payload or {}
                results.append({
                    # Core content
                    "content":       payload.get("content", ""),
                    "source":        payload.get("web_source") or payload.get("source", collection),
                    "citation":      payload.get("citation", ""),
                    "score":         getattr(hit, "score", 0.0),
                    # Hierarchy
                    "chunk_id":      payload.get("chunk_id", ""),
                    "parent_id":     payload.get("parent_id"),
                    "chunk_level":   payload.get("chunk_level", ""),
                    # Classification
                    "category":      payload.get("category", ""),
                    "sub_category":  payload.get("sub_category", ""),
                    "intent_tags":   payload.get("intent_tags", []),
                    "region":        payload.get("region", ""),
                    # Lifecycle
                    "version":       payload.get("version", ""),
                    "is_active":     payload.get("is_active", True),
                    "last_updated":  payload.get("last_updated", ""),
                })

            logger.info("qdrant.retrieve.complete", collection=collection,
                        num_results=len(results), elapsed_ms=elapsed_ms,
                        scores=[round(r["score"], 3) for r in results])
            return results

        except Exception as exc:
            logger.error("qdrant.retrieve.error", collection=collection,
                         error=str(exc), error_type=type(exc).__name__)
            raise

    # ------------------------------------------------------------------
    # Ingestion
    # ------------------------------------------------------------------

    async def add_documents(
        self,
        collection: str,
        documents: List[Dict[str, Any]],
        batch_size: int = 64,
    ):
        """Upsert documents with full metadata payload.

        Each document dict must have at minimum:
          - id:      unique string ID
          - content: text to embed

        All other keys are stored as payload metadata in Qdrant.
        """
        logger.info("qdrant.add_documents.start", collection=collection, count=len(documents))

        texts = [doc.get("content", "") for doc in documents]

        # Batch embedding to avoid OOM on large datasets
        all_embeddings = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i: i + batch_size]
            embeddings = await self.embedder.aembed(batch)
            all_embeddings.extend(embeddings)

        points = []
        for idx, doc in enumerate(documents):
            raw_id = doc.get("id", idx)
            # Qdrant accepts uint64 or UUID; deterministically derive a UUID from string IDs
            if isinstance(raw_id, str):
                point_id = str(_uuid.uuid5(_uuid.NAMESPACE_DNS, raw_id))
            elif isinstance(raw_id, int):
                point_id = raw_id
            else:
                point_id = idx

            # Everything except 'id' goes into payload (including content)
            payload = {k: v for k, v in doc.items() if k != "id"}

            points.append(qm.PointStruct(
                id=point_id,
                vector=all_embeddings[idx],
                payload=payload,
            ))

        # Upsert in batches
        for i in range(0, len(points), batch_size):
            self.client.upsert(collection_name=collection, points=points[i: i + batch_size])

        logger.info("qdrant.add_documents.complete", collection=collection, num_points=len(points))

    async def delete_by_filter(self, collection: str, region: str, version: str):
        """Remove old versions of a region's chunks before re-ingesting."""
        self.client.delete(
            collection_name=collection,
            points_selector=qm.FilterSelector(
                filter=qm.Filter(must=[
                    qm.FieldCondition(key="region", match=qm.MatchValue(value=region)),
                    qm.FieldCondition(key="version", match=qm.MatchValue(value=version)),
                ])
            ),
        )
        logger.info("qdrant.delete_by_filter.complete", collection=collection,
                    region=region, version=version)


# Singleton
_retriever = None


def get_retriever() -> QdrantRetriever:
    global _retriever
    if _retriever is None:
        _retriever = QdrantRetriever()
    return _retriever
