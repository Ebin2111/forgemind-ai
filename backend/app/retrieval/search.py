"""Retrieve relevant passages for a question.

* Keyword search: BM25 over an inverted index (cached until the passages change). Part numbers
  and codes such as "WO-1004" or "ISO VG 46" match exactly, which embeddings alone handle poorly.
* Semantic search: FAISS cosine similarity (when enabled and installed).
* Hybrid: when both find something, results are merged with Reciprocal Rank Fusion.

If semantic search fails for any reason it is logged and keyword results are used instead.
"""
import logging
import math
import re
import threading
from collections import Counter, defaultdict

from . import vector_store

logger = logging.getLogger(__name__)

BM25_K1 = 1.5
BM25_B = 0.75
RRF_K = 60  # standard Reciprocal Rank Fusion constant
MIN_SEMANTIC_SCORE = 0.2  # cosine similarity below this is treated as unrelated
CANDIDATE_FACTOR = 4  # candidates fetched per signal, as a multiple of k
MIN_CANDIDATES = 20

_STOP = {
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "is", "are", "was", "were", "be", "how",
    "what", "when", "why", "which", "who", "do", "does", "did", "i", "my", "we", "our", "you", "your", "with",
    "at", "by", "it", "its", "this", "that", "these", "those", "from", "can", "should", "would", "could",
    "about", "as", "if", "then", "than", "there", "has", "have", "had", "will", "not", "no",
}
_WORD = re.compile(r"[a-z0-9]+")
_COMPOUND = re.compile(r"[a-z0-9]+(?:[-/_.][a-z0-9]+)+")  # CNC-101, WO-1004, 4.5, ISO-VG-46


def _stem(word: str) -> str:
    """Deliberately light stemming so 'replacing', 'replaced' and 'replace' share a term."""
    if len(word) > 4 and word.endswith("ies"):
        word = word[:-3] + "y"
    elif len(word) > 5 and word.endswith("ing"):
        word = word[:-3]
    elif len(word) > 4 and word.endswith("ed"):
        word = word[:-2]
    elif len(word) > 4 and word.endswith(("sses", "xes", "ches", "shes")):
        word = word[:-2]
    elif len(word) > 3 and word.endswith("s") and not word.endswith(("ss", "us", "is")):
        word = word[:-1]
    return word[:-1] if len(word) > 4 and word.endswith("e") else word


def tokenize(text: str) -> list[str]:
    """Words (stopwords removed, stemmed) plus whole codes like 'wo-1004' as extra exact-match terms."""
    text = text.lower()
    tokens = [
        _stem(w) for w in _WORD.findall(text) if w not in _STOP and (len(w) > 1 or w.isdigit())
    ]
    tokens.extend(_COMPOUND.findall(text))
    return tokens


class KeywordIndex:
    """BM25 inverted index over passages (document names are searchable too)."""

    def __init__(self, chunks: list[dict]):
        self.chunks = chunks
        self._tf: list[Counter] = []
        self._len: list[int] = []
        self._postings: dict[str, list[int]] = defaultdict(list)
        for i, chunk in enumerate(chunks):
            tf = Counter(tokenize(chunk["text"]))
            tf.update(tokenize(chunk.get("document", "")))
            self._tf.append(tf)
            self._len.append(sum(tf.values()))
            for term in tf:
                self._postings[term].append(i)
        self._avg_len = (sum(self._len) / len(chunks)) if chunks else 0.0

    def search(self, query: str, k: int) -> list[tuple[dict, float]]:
        n = len(self.chunks)
        scores: dict[int, float] = defaultdict(float)
        for term in set(tokenize(query)):
            docs = self._postings.get(term)
            if not docs:
                continue
            idf = math.log(1 + (n - len(docs) + 0.5) / (len(docs) + 0.5))
            for i in docs:
                f = self._tf[i][term]
                norm = f * (BM25_K1 + 1) / (f + BM25_K1 * (1 - BM25_B + BM25_B * self._len[i] / (self._avg_len or 1)))
                scores[i] += idf * norm
        ranked = sorted(scores.items(), key=lambda item: (-item[1], item[0]))[:k]
        return [(self.chunks[i], s) for i, s in ranked]


_index_lock = threading.Lock()
_cached_index: KeywordIndex | None = None


def _keyword_index(chunks: list[dict]) -> KeywordIndex:
    """Reuse the index while the store hands back the same (cached) passage list."""
    global _cached_index
    cached = _cached_index
    if cached is not None and cached.chunks is chunks:
        return cached
    with _index_lock:
        if _cached_index is None or _cached_index.chunks is not chunks:
            _cached_index = KeywordIndex(chunks)
        return _cached_index


def keyword_search(query: str, chunks: list[dict], k: int) -> list[dict]:
    """BM25 search over the given passages. Returns passages with a 'score' key, best first."""
    if not query.strip() or not chunks:
        return []
    return [{**c, "score": round(s, 4)} for c, s in KeywordIndex(chunks).search(query, k)]


def _key(chunk: dict) -> tuple:
    return chunk["document"], chunk["page"], chunk.get("chunk_index"), chunk["text"]


def reciprocal_rank_fusion(rankings: list[list[tuple[dict, float]]], k: int) -> list[dict]:
    """Merge ranked lists. Scores are scaled to 0..1 (1.0 = ranked first in every list)."""
    fused: dict[tuple, float] = defaultdict(float)
    by_key: dict[tuple, dict] = {}
    for ranking in rankings:
        for rank, (chunk, _score) in enumerate(ranking, start=1):
            key = _key(chunk)
            fused[key] += 1.0 / (RRF_K + rank)
            by_key[key] = chunk
    best_possible = len(rankings) / (RRF_K + 1)
    ordered = sorted(fused.items(), key=lambda item: -item[1])[:k]
    return [{**by_key[key], "score": round(score / best_possible, 4)} for key, score in ordered]


def search(query: str, k: int = 4) -> tuple[list[dict], str]:
    """Return (passages, mode); mode is 'keyword', 'semantic' or 'hybrid'.

    Each passage is {"document", "page", "chunk_index", "text", "score"}. Scores are only
    comparable within one response (BM25 is unbounded; semantic is cosine; hybrid is 0..1).
    """
    query = (query or "").strip()
    chunks = vector_store.load_chunks()
    if not query or not chunks:
        return [], "keyword"

    pool = max(k * CANDIDATE_FACTOR, MIN_CANDIDATES)
    keyword_hits = _keyword_index(chunks).search(query, pool)

    semantic_hits: list[tuple[dict, float]] = []
    if vector_store.semantic_enabled():
        try:
            semantic_hits = [(c, s) for c, s in vector_store.semantic_query(query, pool) if s >= MIN_SEMANTIC_SCORE]
        except Exception:
            logger.warning("Semantic search failed; using keyword results", exc_info=True)

    if semantic_hits and keyword_hits:
        return reciprocal_rank_fusion([semantic_hits, keyword_hits], k), "hybrid"
    if semantic_hits:
        return [{**c, "score": round(s, 4)} for c, s in semantic_hits[:k]], "semantic"
    return [{**c, "score": round(s, 4)} for c, s in keyword_hits[:k]], "keyword"