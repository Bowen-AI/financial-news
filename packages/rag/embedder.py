"""Local sentence-transformers embedding model wrapper."""
from __future__ import annotations

from functools import lru_cache
from typing import Sequence

import numpy as np


@lru_cache(maxsize=1)
def _load_model(model_name: str):
    """Load and cache the embedding model (lazy)."""
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(model_name)


class EmbeddingModel:
    """Thin wrapper around sentence-transformers for batch embedding."""

    def __init__(self, model_name: str = "BAAI/bge-small-en-v1.5") -> None:
        self.model_name = model_name

    @property
    def _model(self):
        return _load_model(self.model_name)

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """Return a list of embedding vectors (one per text)."""
        if not texts:
            return []
        vecs: np.ndarray = self._model.encode(
            list(texts),
            normalize_embeddings=True,
            batch_size=32,
            show_progress_bar=False,
        )
        return vecs.tolist()

    def embed_one(self, text: str) -> list[float]:
        return self.embed([text])[0]
