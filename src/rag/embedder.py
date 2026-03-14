"""Multilingual sentence-transformers embedder"""
from typing import List
import numpy as np


class Embedder:
    """Sentence transformer embedder for RAG"""

    def __init__(self, model_name: str = "paraphrase-multilingual-MiniLM-L12-v2", device: str = "mps"):
        self.model_name = model_name
        self.device = device
        self.model = None
        self._load_model()

    def _load_model(self):
        try:
            from sentence_transformers import SentenceTransformer
            self.model = SentenceTransformer(self.model_name, device=self.device)
        except Exception:
            self.model = None

    def embed(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for texts

        Returns:
            List of embedding vectors
        """
        if isinstance(texts, str):
            texts = [texts]

        if self.model is None:
            # Fallback deterministic vector if model is unavailable
            return [[0.1] * 384 for _ in texts]

        emb = self.model.encode(texts, convert_to_numpy=True)
        return emb.tolist()

    async def aembed(self, texts: List[str]) -> List[List[float]]:
        """Async embedding"""
        return self.embed(texts)


# Singleton
_embedder = None


def get_embedder() -> Embedder:
    """Get or create the embedder"""
    global _embedder
    if _embedder is None:
        _embedder = Embedder()
    return _embedder