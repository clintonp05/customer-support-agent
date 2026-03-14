"""Qdrant semantic search retriever"""
from typing import List, Dict, Any
from qdrant_client import QdrantClient
from qdrant_client.http import models as qdrant_models

from src.rag.embedder import get_embedder
from src.config import settings


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
        ]
        for c in collections:
            try:
                self.client.get_collection(c["name"])
            except Exception:
                try:
                    self.client.recreate_collection(
                        collection_name=c["name"],
                        vectors_config=c["vectors"],
                        shard_number=1,
                    )
                except Exception:
                    try:
                        self.client.create_collection(
                            collection_name=c["name"],
                            vectors_config=c["vectors"],
                            shard_number=1,
                        )
                    except Exception:
                        pass

    async def retrieve(
        self,
        query: str,
        collection: str,
        limit: int = 5,
        score_threshold: float = 0.0
    ) -> List[Dict[str, Any]]:
        """Retrieve relevant documents from Qdrant"""
        query_embedding = await self.embedder.aembed([query])
        query_vector = query_embedding[0]

        search_result = self.client.search(
            collection_name=collection,
            query_vector=query_vector,
            limit=limit,
            with_payload=True,
            score_threshold=score_threshold,
        )

        return [
            {
                "content": hit.payload.get("content", "") if hit.payload else "",
                "source": hit.payload.get("source", "") if hit.payload else collection,
                "score": hit.score,
            }
            for hit in search_result
        ]

    async def add_documents(self, collection: str, documents: List[Dict[str, str]]):
        """Add documents to Qdrant collection"""
        texts = [doc.get("content", "") for doc in documents]
        embeddings = await self.embedder.aembed(texts)

        points = []
        for idx, doc in enumerate(documents):
            points.append(
                qdrant_models.PointStruct(
                    id=doc.get("id", idx),
                    vector=embeddings[idx],
                    payload={
                        "content": doc.get("content", ""),
                        "source": doc.get("source", "unknown")
                    },
                )
            )

        self.client.upsert(collection_name=collection, points=points)


# Singleton
_retriever = None


def get_retriever() -> QdrantRetriever:
    """Get or create the retriever"""
    global _retriever
    if _retriever is None:
        _retriever = QdrantRetriever()
    return _retriever