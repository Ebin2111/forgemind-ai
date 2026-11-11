"""Persistent passage store with an optional FAISS index kept consistent with it.

Files:
    data/processed/chunks.json     passages: [{"document", "page", "chunk_index", "text"}, ...]
    data/indexes/faiss.index       one unit-length vector per passage, in the same order
    data/indexes/index_meta.json   which embedding model / dimension built the index

Guarantees:
  * Writes are atomic (temp file + rename), index first and chunks last.
  * Adding documents embeds only the NEW passages; removing a document reuses the stored
    vectors (no re-embedding).
  * The index file exists only while it matches the passages. If it is missing, out of sync
    (crash, manual edit, semantic search toggled) or built by another model, it is rebuilt
    automatically the next time it is needed.
  * A corrupt chunks file raises VectorStoreError instead of being silently overwritten.

Concurrency: a process-wide lock serialises writers and index access. Run a single worker
process per data directory (use a real vector database for multi-process deployments).
"""
import importlib.util
import json
import logging
import os
import threading
from functools import lru_cache
from pathlib import Path
from typing import Any

from ..core.config import settings
from . import embeddings

logger = logging.getLogger(__name__)

CHUNKS_FILE = settings.processed_dir / "chunks.json"
INDEX_FILE = settings.indexes_dir / "faiss.index"
META_FILE = settings.indexes_dir / "index_meta.json"

_lock = threading.RLock()
_chunks_cache: tuple[tuple[int, int], list[dict]] | None = None
_index_cache: tuple[tuple[int, int], Any] | None = None


class VectorStoreError(RuntimeError):
    """The passage store on disk is unreadable."""


# --- capability checks -------------------------------------------------------
@lru_cache(maxsize=None)
def _module_available(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def faiss_available() -> bool:
    return _module_available("faiss")


def semantic_enabled() -> bool:
    """Semantic search is on when configured AND both optional packages are installed."""
    return settings.enable_semantic_search and embeddings.embeddings_available() and faiss_available()


# --- file helpers --------------------------------------------------------------
def _stamp(path: Path) -> tuple[int, int] | None:
    try:
        st = path.stat()
    except FileNotFoundError:
        return None
    return st.st_mtime_ns, st.st_size


def _tmp_path(path: Path) -> Path:
    return path.with_name(f".{path.name}.{os.getpid()}.tmp")


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = _tmp_path(path)
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def reset_caches() -> None:
    """Forget in-memory copies (used by tests, or after editing the files by hand)."""
    global _chunks_cache, _index_cache
    with _lock:
        _chunks_cache = None
        _index_cache = None


# --- passages ------------------------------------------------------------------
def load_chunks() -> list[dict]:
    """All stored passages. The returned list is shared and cached: treat it as read-only."""
    global _chunks_cache
    stamp = _stamp(CHUNKS_FILE)
    if stamp is None:
        return []
    cached = _chunks_cache
    if cached and cached[0] == stamp:
        return cached[1]
    with _lock:
        try:
            chunks = json.loads(CHUNKS_FILE.read_text(encoding="utf-8"))
            if not isinstance(chunks, list):
                raise ValueError("expected a JSON list")
        except (OSError, ValueError) as exc:
            raise VectorStoreError(f"Cannot read {CHUNKS_FILE}: {exc}") from exc
        _chunks_cache = (_stamp(CHUNKS_FILE) or stamp, chunks)
        return chunks


# --- FAISS index ---------------------------------------------------------------
def _read_index():
    """Index from memory or disk; None if absent or unreadable."""
    global _index_cache
    stamp = _stamp(INDEX_FILE)
    if stamp is None:
        _index_cache = None
        return None
    if _index_cache and _index_cache[0] == stamp:
        return _index_cache[1]
    import faiss

    try:
        index = faiss.read_index(str(INDEX_FILE))
    except Exception:
        logger.warning("Could not read FAISS index %s; it will be rebuilt", INDEX_FILE, exc_info=True)
        return None
    _index_cache = (stamp, index)
    return index


def _meta_matches(index) -> bool:
    try:
        meta = json.loads(META_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return meta.get("model") == settings.embedding_model and meta.get("dim") == index.d


def _new_index(dim: int):
    import faiss

    return faiss.IndexFlatIP(dim)  # inner product on unit vectors == cosine similarity


def _build_index(chunks: list[dict]):
    """Embed every passage from scratch. Slow; only used for first build or self-healing."""
    if not chunks:
        return None
    logger.info("Building FAISS index for %d passages with %s", len(chunks), settings.embedding_model)
    vectors = embeddings.embed_texts([c["text"] for c in chunks])
    index = _new_index(vectors.shape[1])
    index.add(vectors)
    return index


def _ensure_index(chunks: list[dict]):
    """Return an index aligned with ``chunks`` (rebuilding if needed); None when there are no passages."""
    if not chunks:
        return None
    index = _read_index()
    if index is not None and index.ntotal == len(chunks) and _meta_matches(index):
        return index
    if index is not None:
        logger.warning("FAISS index out of sync (%d vectors, %d passages); rebuilding", index.ntotal, len(chunks))
    index = _build_index(chunks)
    _commit(chunks, index)
    return index


def _commit(chunks: list[dict], index) -> None:
    """Persist state: index and metadata first, passages last. A crash in between is self-healing."""
    global _chunks_cache, _index_cache
    if index is not None and index.ntotal == len(chunks):
        import faiss

        INDEX_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = _tmp_path(INDEX_FILE)
        faiss.write_index(index, str(tmp))
        os.replace(tmp, INDEX_FILE)
        _atomic_write_text(META_FILE, json.dumps({"model": settings.embedding_model, "dim": index.d, "count": index.ntotal}))
        _index_cache = (_stamp(INDEX_FILE), index)
    else:  # no valid index for these passages: remove any stale one
        INDEX_FILE.unlink(missing_ok=True)
        META_FILE.unlink(missing_ok=True)
        _index_cache = None
    _atomic_write_text(CHUNKS_FILE, json.dumps(chunks, ensure_ascii=False))
    _chunks_cache = (_stamp(CHUNKS_FILE), chunks)


# --- public operations ---------------------------------------------------------
def add_chunks(new_chunks: list[dict]) -> int:
    """Append passages (embedding only the new ones). Returns the total passage count.

    Nothing is written if embedding fails, so a failed upload leaves the store unchanged.
    """
    with _lock:
        existing = load_chunks()
        if not new_chunks:
            return len(existing)
        chunks = [*existing, *new_chunks]
        try:
            index = None
            if semantic_enabled():
                index = _ensure_index(existing)
                vectors = embeddings.embed_texts([c["text"] for c in new_chunks])
                if index is None:
                    index = _new_index(vectors.shape[1])
                index.add(vectors)
            _commit(chunks, index)
        except Exception:
            reset_caches()  # in-memory index may have been mutated; reload from disk next time
            raise
        return len(chunks)


def remove_document(document: str) -> int:
    """Drop every passage of a document, reusing stored vectors. Returns the remaining count."""
    with _lock:
        chunks = load_chunks()
        keep = [i for i, c in enumerate(chunks) if c["document"] != document]
        if len(keep) == len(chunks):
            return len(chunks)
        kept = [chunks[i] for i in keep]

        index = None
        if kept and semantic_enabled():
            old = _read_index()
            if old is not None and old.ntotal == len(chunks) and _meta_matches(old):
                index = _new_index(old.d)
                index.add(old.reconstruct_n(0, old.ntotal)[keep])
            # otherwise the stale index is deleted by _commit and rebuilt lazily
        _commit(kept, index)
        return len(kept)


def semantic_query(query: str, k: int) -> list[tuple[dict, float]]:
    """Top-k passages by cosine similarity: [(passage, score)], best first. Raises EmbeddingError."""
    query_vector = embeddings.embed_texts([query])  # outside the lock: model inference can be slow
    with _lock:
        chunks = load_chunks()
        index = _ensure_index(chunks)
        if index is None or index.ntotal == 0:
            return []
        scores, ids = index.search(query_vector, min(k, index.ntotal))
        return [(chunks[int(i)], float(s)) for i, s in zip(ids[0], scores[0]) if i >= 0]


def rebuild_index() -> int:
    """Re-embed everything (e.g. after changing EMBEDDING_MODEL). Returns the vector count."""
    with _lock:
        if not semantic_enabled():
            raise VectorStoreError("Semantic search is not enabled or its dependencies are missing.")
        chunks = load_chunks()
        index = _build_index(chunks)
        _commit(chunks, index)
        return index.ntotal if index is not None else 0


def stats() -> dict:
    chunks = load_chunks()
    index = _read_index() if faiss_available() and INDEX_FILE.exists() else None
    return {
        "passages": len(chunks),
        "documents": len({c["document"] for c in chunks}),
        "semantic_enabled": semantic_enabled(),
        "indexed_vectors": index.ntotal if index is not None else 0,
        "embedding_model": settings.embedding_model,
    }