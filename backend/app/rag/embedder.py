"""Embedding wrapper bound to the configured model and its real dimension."""

from __future__ import annotations

import logging
from typing import Optional

import numpy as np

from app.config import settings

logger = logging.getLogger(__name__)
DEFAULT_E5_MODEL = "intfloat/multilingual-e5-large"
DEFAULT_E5_REVISION = "3d7cfbdacd47fdda877c5cd8a79fbcc4f2a574f3"

_embedder_instance: Optional["Embedder"] = None


class Embedder:
    """E5 uses query/passage prefixes; other models receive plain text."""

    def __init__(self) -> None:
        self.model_name = settings.EMBEDDING_MODEL
        self.revision = settings.EMBEDDING_REVISION or (
            DEFAULT_E5_REVISION if self.model_name == DEFAULT_E5_MODEL else ""
        )
        self._uses_e5_prefix = "/e5-" in self.model_name or "/multilingual-e5-" in self.model_name
        logger.info("Loading embedding model: %s", self.model_name)
        try:
            from sentence_transformers import SentenceTransformer
            kwargs = {"revision": self.revision} if self.revision else {}
            self._model = SentenceTransformer(self.model_name, **kwargs)
            dimension = self._model.get_embedding_dimension()
            if not isinstance(dimension, int) or dimension <= 0:
                dimension = len(self._model.encode("dimension probe"))
            self._dim = dimension
            logger.info("Embedding model loaded. Dim=%d", self._dim)
        except ImportError as exc:
            raise RuntimeError(
                "sentence-transformers is not installed. "
                "Run: uv add sentence-transformers"
            ) from exc

    @classmethod
    def get(cls) -> "Embedder":
        global _embedder_instance
        if _embedder_instance is None:
            _embedder_instance = cls()
        return _embedder_instance

    def embed_query(self, query: str) -> list[float]:
        value = query.strip()
        text = f"query: {value}" if self._uses_e5_prefix else value
        vec: np.ndarray = self._model.encode(text, normalize_embeddings=True)
        return vec.tolist()

    def embed_passage(self, text: str) -> list[float]:
        value = text.strip()
        value = f"passage: {value}" if self._uses_e5_prefix else value
        vec: np.ndarray = self._model.encode(value, normalize_embeddings=True)
        return vec.tolist()

    def embed_passages(self, texts: list[str], batch_size: int = 32) -> list[list[float]]:
        prefixed = [f"passage: {t.strip()}" if self._uses_e5_prefix else t.strip() for t in texts]
        vecs: np.ndarray = self._model.encode(
            prefixed,
            batch_size=batch_size,
            normalize_embeddings=True,
            show_progress_bar=len(texts) > 50,
        )
        return vecs.tolist()

    @property
    def dim(self) -> int:
        return self._dim
