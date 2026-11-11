"""Text embeddings via Sentence Transformers (optional dependency).

The model is loaded lazily, once per process, and shared across threads. Vectors are returned
L2-normalised so that an inner-product FAISS index gives cosine similarity.
"""
import importlib.util
import logging
import threading
import time
from collections.abc import Sequence
from functools import lru_cache

from ..core.config import settings

logger = logging.getLogger(__name__)

DEFAULT_BATCH_SIZE = 32

_model = None
_model_lock = threading.Lock()


class EmbeddingError(RuntimeError):
    """The embedding model is unavailable or failed. Callers should fall back to keyword search."""


@lru_cache(maxsize=None)
def _module_available(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def embeddings_available() -> bool:
    """True if sentence-transformers is installed (checked without importing the heavy package)."""
    return _module_available("sentence_transformers")


def get_model():
    """Load the configured model on first use (thread-safe)."""
    global _model
    if _model is not None:
        return _model
    with _model_lock:
        if _model is None:
            if not embeddings_available():
                raise EmbeddingError("sentence-transformers is not installed (pip install sentence-transformers).")
            try:
                from sentence_transformers import SentenceTransformer

                started = time.perf_counter()
                _model = SentenceTransformer(settings.embedding_model)
                logger.info("Loaded embedding model %s in %.1fs", settings.embedding_model, time.perf_counter() - started)
            except Exception as exc:
                raise EmbeddingError(f"Could not load embedding model '{settings.embedding_model}': {exc}") from exc
    return _model


def embedding_dimension() -> int:
    return int(get_model().get_sentence_embedding_dimension())


def embed_texts(texts: Sequence[str], batch_size: int = DEFAULT_BATCH_SIZE):
    """Return a C-contiguous float32 array of shape (len(texts), dim) with unit-length rows."""
    import numpy as np

    texts = list(texts)
    if not texts:
        return np.zeros((0, 0), dtype="float32")
    model = get_model()
    try:
        vectors = model.encode(
            texts,
            batch_size=batch_size,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
    except Exception as exc:
        raise EmbeddingError(f"Embedding {len(texts)} text(s) failed: {exc}") from exc
    return np.ascontiguousarray(vectors, dtype="float32")


def embed_query(text: str):
    """Embed one query. Shape (1, dim)."""
    return embed_texts([text])