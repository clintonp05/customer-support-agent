"""Multilingual E5 embedder (intfloat/multilingual-e5-base, 768-dim).

E5 models require prefixes:
  - Ingestion (passages): "passage: <text>"
  - Retrieval (queries):  "query: <text>"

Output dimension: 768 (upgraded from 384).
"""
from typing import List


class Embedder:
    """Sentence-transformer embedder using multilingual-e5-base."""

    MODEL_NAME = "intfloat/multilingual-e5-base"
    DIM = 768

    def __init__(self, device: str = "mps"):
        self.device = device
        self.model = None
        self._load_model()

    def _load_model(self):
        try:
            from sentence_transformers import SentenceTransformer
            self.model = SentenceTransformer(self.MODEL_NAME, device=self.device)
        except Exception:
            self.model = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _add_passage_prefix(self, texts: List[str]) -> List[str]:
        return [f"passage: {t}" for t in texts]

    def _add_query_prefix(self, texts: List[str]) -> List[str]:
        return [f"query: {t}" for t in texts]

    def _encode(self, texts: List[str]) -> List[List[float]]:
        if self.model is None:
            return [[0.1] * self.DIM for _ in texts]
        emb = self.model.encode(texts, convert_to_numpy=True, normalize_embeddings=True)
        return emb.tolist()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def embed(self, texts: List[str]) -> List[List[float]]:
        """Embed passages for ingestion (adds 'passage: ' prefix)."""
        if isinstance(texts, str):
            texts = [texts]
        return self._encode(self._add_passage_prefix(texts))

    def embed_query(self, texts: List[str]) -> List[List[float]]:
        """Embed queries for retrieval (adds 'query: ' prefix)."""
        if isinstance(texts, str):
            texts = [texts]
        return self._encode(self._add_query_prefix(texts))

    async def aembed(self, texts: List[str]) -> List[List[float]]:
        """Async passage embedding (used by retriever.add_documents)."""
        return self.embed(texts)

    async def aembed_query(self, texts: List[str]) -> List[List[float]]:
        """Async query embedding (used by retriever.retrieve)."""
        return self.embed_query(texts)


# Singleton
_embedder = None


def get_embedder() -> Embedder:
    global _embedder
    if _embedder is None:
        _embedder = Embedder()
    return _embedder
