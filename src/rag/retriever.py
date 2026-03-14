"""Qdrant semantic search retriever"""
from typing import List, Dict, Any
from qdrant_client import QdrantClient
from qdrant_client.http import models as qdrant_models

from src.rag.embedder import get_embedder
from src.config import settings
from src.observability.logger import get_logger

logger = get_logger()


class QdrantRetriever:
    """Qdrant-backed semantic retriever"""

    def __init__(self, client: QdrantClient = None):
        self.client = client or QdrantClient(url=settings.qdrant_url)
        self.embedder = get_embedder()
        self._ensure_collections()

    def _ensure_collections(self):
        collections = [
            {
                "name": "noon_intents",
                "vectors": qdrant_models.VectorParams(size=384, distance=qdrant_models.Distance.COSINE),
            },
            {
                "name": "noon_faq",
                "vectors": qdrant_models.VectorParams(size=384, distance=qdrant_models.Distance.COSINE),
            },
            {
                "name": "noon_policies",
                "vectors": qdrant_models.VectorParams(size=384, distance=qdrant_models.Distance.COSINE),
            },
        ]
        for c in collections:
            try:
                self.client.get_collection(c["name"])
                logger.info("qdrant.collection_exists", collection=c["name"])
            except Exception:
                try:
                    self.client.recreate_collection(
                        collection_name=c["name"],
                        vectors_config=c["vectors"],
                        shard_number=1,
                    )
                    logger.info("qdrant.collection_created", collection=c["name"])
                except Exception:
                    try:
                        self.client.create_collection(
                            collection_name=c["name"],
                            vectors_config=c["vectors"],
                            shard_number=1,
                        )
                        logger.info("qdrant.collection_created", collection=c["name"])
                    except Exception as e:
                        logger.warning("qdrant.collection_create_failed", collection=c["name"], error=str(e))

    async def retrieve(
        self,
        query: str,
        collection: str,
        limit: int = 5,
        score_threshold: float = 0.0
    ) -> List[Dict[str, Any]]:
        """Retrieve relevant documents from Qdrant"""
        import time
        start = time.time()

        logger.info("qdrant.retrieve.start", query=query[:50], collection=collection, limit=limit)

        try:
            query_embedding = await self.embedder.aembed([query])
            query_vector = query_embedding[0]

            query_response = self.client.query_points(
                collection_name=collection,
                query=query_vector,
                limit=limit,
                with_payload=True,
                score_threshold=score_threshold,
            )

            # query_points returns a QueryResponse object with `result` points
            points = getattr(query_response, "points", [])
            elapsed_ms = int((time.time() - start) * 1000)

            results = [
                {
                    "content": (hit.payload.get("content", "") if hit.payload else "") if hasattr(hit, "payload") else "",
                    "source": (hit.payload.get("source", "") if hit.payload else collection) if hasattr(hit, "payload") else collection,
                    "score": getattr(hit, "score", 0.0),
                }
                for hit in points
            ]

            logger.info("qdrant.retrieve.complete", collection=collection, num_results=len(results), elapsed_ms=elapsed_ms)
            return results

        except Exception as e:
            logger.error("qdrant.retrieve.error", collection=collection, error=str(e), error_type=type(e).__name__)
            raise

    async def add_documents(self, collection: str, documents: List[Dict[str, str]]):
        """Add documents to Qdrant collection"""
        logger.info("qdrant.add_documents.start", collection=collection, num_documents=len(documents))

        texts = [doc.get("content", "") for doc in documents]
        embeddings = await self.embedder.aembed(texts)

        points = []
        for idx, doc in enumerate(documents):
            point_id = doc.get("id", idx)
            if isinstance(point_id, str):
                try:
                    import uuid
                    point_id = uuid.UUID(point_id)
                except Exception:
                    point_id = idx

            points.append(
                qdrant_models.PointStruct(
                    id=point_id,
                    vector=embeddings[idx],
                    payload={
                        "content": doc.get("content", ""),
                        "source": doc.get("source", "unknown")
                    },
                )
            )

        self.client.upsert(collection_name=collection, points=points)
        logger.info("qdrant.add_documents.complete", collection=collection, num_points=len(points))


# Singleton
_retriever = None


def get_retriever() -> QdrantRetriever:
    """Get or create the retriever"""
    global _retriever
    if _retriever is None:
        _retriever = QdrantRetriever()
    return _retriever