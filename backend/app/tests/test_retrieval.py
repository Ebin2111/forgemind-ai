import hashlib
import json

import pytest

from backend.app.core.config import settings
from backend.app.retrieval import embeddings, search, vector_store
from backend.app.retrieval.search import KeywordIndex, keyword_search, reciprocal_rank_fusion, tokenize


def chunk(document, page, text, index=0):
    return {"document": document, "page": page, "chunk_index": index, "text": text}


CORPUS = [
    chunk("compressor.pdf", 1, "Replace the oil separator element every 4000 operating hours."),
    chunk("compressor.pdf", 2, "Check belt tension monthly and drain condensate from the receiver daily."),
    chunk("press.pdf", 5, "Hydraulic press uses ISO VG 46 oil. Replace rod seals if the cylinder leaks."),
    chunk("robot.pdf", 3, "Servo alarm on axis 3: inspect the encoder cable and motor brake."),
    chunk("wo-notes.pdf", 1, "Work order WO-1004 closed after rod seal replacement on press PRS-401."),
]


@pytest.fixture()
def store(tmp_path, monkeypatch):
    """An isolated passage store in a temp directory with semantic search off."""
    monkeypatch.setattr(vector_store, "CHUNKS_FILE", tmp_path / "processed" / "chunks.json")
    monkeypatch.setattr(vector_store, "INDEX_FILE", tmp_path / "indexes" / "faiss.index")
    monkeypatch.setattr(vector_store, "META_FILE", tmp_path / "indexes" / "index_meta.json")
    monkeypatch.setattr(settings, "enable_semantic_search", False)
    vector_store.reset_caches()
    yield vector_store
    vector_store.reset_caches()


# --- tokenizer ------------------------------------------------------------
def test_tokenize_stems_removes_stopwords_and_keeps_codes():
    assert set(tokenize("replacing")) == set(tokenize("replaced")) == set(tokenize("replace"))
    assert "the" not in tokenize("the oil") and "oil" in tokenize("the oil")
    toks = tokenize("See WO-1004 for CNC-101")
    assert "wo-1004" in toks and "cnc-101" in toks and "1004" in toks
    assert "seals" not in tokenize("seals") and "seal" in tokenize("seals")


# --- BM25 -----------------------------------------------------------------
def test_bm25_ranks_the_relevant_passage_first():
    hits = keyword_search("how often replace the oil separator", CORPUS, 3)
    assert hits[0]["document"] == "compressor.pdf" and hits[0]["page"] == 1
    assert hits == sorted(hits, key=lambda h: -h["score"])


def test_exact_code_match_beats_generic_terms():
    hits = keyword_search("WO-1004", CORPUS, 2)
    assert hits[0]["document"] == "wo-notes.pdf"


def test_rare_terms_outweigh_common_terms():
    hits = keyword_search("encoder oil", CORPUS, 2)  # 'encoder' appears once, 'oil' in several
    assert hits[0]["document"] == "robot.pdf"


def test_document_name_is_searchable():
    assert keyword_search("robot", CORPUS, 1)[0]["document"] == "robot.pdf"


@pytest.mark.parametrize("query", ["", "   ", "the of and", "zzzzqqq"])
def test_no_match_or_blank_query_returns_nothing(query):
    assert keyword_search(query, CORPUS, 3) == []
    assert KeywordIndex([]).search("oil", 3) == []


# --- reciprocal rank fusion ------------------------------------------------
def test_rrf_rewards_agreement_and_scales_to_one():
    a, b, c = CORPUS[0], CORPUS[1], CORPUS[2]
    fused = reciprocal_rank_fusion([[(a, 0.9), (b, 0.5)], [(a, 5.0), (c, 3.0)]], 3)
    assert fused[0]["text"] == a["text"] and fused[0]["score"] == 1.0
    assert {f["text"] for f in fused} == {a["text"], b["text"], c["text"]}


# --- passage store (keyword mode) -----------------------------------------
def test_store_roundtrip_remove_and_cache(store):
    assert store.load_chunks() == []
    assert store.add_chunks(CORPUS[:3]) == 3
    assert store.add_chunks([]) == 3
    assert store.add_chunks(CORPUS[3:]) == 5

    store.reset_caches()  # force a reload from disk, as a new process would
    assert [c["text"] for c in store.load_chunks()] == [c["text"] for c in CORPUS]
    assert store.load_chunks() is store.load_chunks()  # cached while the file is unchanged

    assert store.remove_document("compressor.pdf") == 3
    assert store.remove_document("does-not-exist.pdf") == 3
    assert all(c["document"] != "compressor.pdf" for c in store.load_chunks())
    assert not list(store.CHUNKS_FILE.parent.glob(".*.tmp"))  # no temp files left behind


def test_corrupt_store_raises_and_is_never_overwritten(store):
    store.CHUNKS_FILE.parent.mkdir(parents=True)
    store.CHUNKS_FILE.write_text("{ not json", encoding="utf-8")
    with pytest.raises(vector_store.VectorStoreError):
        store.load_chunks()
    with pytest.raises(vector_store.VectorStoreError):
        store.add_chunks(CORPUS[:1])
    assert store.CHUNKS_FILE.read_text(encoding="utf-8") == "{ not json"


def test_search_uses_keyword_mode_and_reflects_store_changes(store):
    assert search.search("oil separator") == ([], "keyword")
    store.add_chunks(CORPUS)
    results, mode = search.search("oil separator hours", k=2)
    assert mode == "keyword" and results[0]["document"] == "compressor.pdf"
    assert {"document", "page", "text", "score"} <= results[0].keys()

    store.remove_document("compressor.pdf")
    results, _ = search.search("oil separator hours", k=2)
    assert all(r["document"] != "compressor.pdf" for r in results)


# --- embeddings module without the optional package ------------------------
def test_embeddings_raise_clear_error_when_package_missing():
    if embeddings.embeddings_available():
        pytest.skip("sentence-transformers is installed")
    assert not vector_store.semantic_enabled()
    with pytest.raises(embeddings.EmbeddingError, match="not installed"):
        embeddings.embed_texts(["hello"])


# --- semantic path: real FAISS, deterministic fake embedder ----------------
faiss = pytest.importorskip("faiss")
np = pytest.importorskip("numpy")

DIM = 64


def fake_embed(texts, batch_size=32):
    """Hashed bag-of-words, unit length: texts sharing words are close in cosine space."""
    out = np.zeros((len(texts), DIM), dtype="float32")
    for row, text in enumerate(texts):
        for token in tokenize(text):
            out[row, int(hashlib.md5(token.encode()).hexdigest(), 16) % DIM] += 1.0
        norm = np.linalg.norm(out[row])
        if norm:
            out[row] /= norm
    return out


@pytest.fixture()
def semantic(store, monkeypatch):
    calls = []

    def counting_embed(texts, batch_size=32):
        calls.append(list(texts))
        return fake_embed(texts)

    monkeypatch.setattr(settings, "enable_semantic_search", True)
    monkeypatch.setattr(embeddings, "embeddings_available", lambda: True)
    monkeypatch.setattr(embeddings, "embed_texts", counting_embed)
    store.embed_calls = calls
    return store


def index_size():
    return faiss.read_index(str(vector_store.INDEX_FILE)).ntotal


def test_semantic_enabled_requires_config_and_packages(semantic, monkeypatch):
    assert semantic.semantic_enabled()
    monkeypatch.setattr(settings, "enable_semantic_search", False)
    assert not semantic.semantic_enabled()


def test_adding_embeds_only_new_passages(semantic):
    semantic.add_chunks(CORPUS[:3])
    semantic.add_chunks(CORPUS[3:])
    assert [len(c) for c in semantic.embed_calls] == [3, 2]  # never re-embeds earlier passages
    assert index_size() == 5
    assert json.loads(vector_store.META_FILE.read_text())["dim"] == DIM


def test_removing_reuses_stored_vectors_without_embedding(semantic):
    semantic.add_chunks(CORPUS)
    calls_before = len(semantic.embed_calls)
    assert semantic.remove_document("press.pdf") == 4
    assert len(semantic.embed_calls) == calls_before  # no new embedding calls
    assert index_size() == 4

    hits = semantic.semantic_query("encoder cable motor brake", 1)
    assert hits[0][0]["document"] == "robot.pdf"  # vectors stayed aligned with passages after removal


def test_removing_last_document_deletes_the_index(semantic):
    semantic.add_chunks(CORPUS[:2])
    semantic.remove_document("compressor.pdf")
    assert semantic.load_chunks() == []
    assert not vector_store.INDEX_FILE.exists() and not vector_store.META_FILE.exists()


def test_semantic_query_ranks_by_similarity(semantic):
    semantic.add_chunks(CORPUS)
    hits = semantic.semantic_query("servo alarm encoder", 2)
    assert hits[0][0]["document"] == "robot.pdf"
    assert hits[0][1] >= hits[1][1]


def test_missing_index_is_rebuilt_lazily(semantic):
    semantic.add_chunks(CORPUS)
    vector_store.INDEX_FILE.unlink()
    semantic.reset_caches()
    assert semantic.semantic_query("oil separator", 1)[0][0]["document"] == "compressor.pdf"
    assert index_size() == 5


def test_out_of_sync_index_is_rebuilt(semantic):
    semantic.add_chunks(CORPUS[:2])
    # Simulate a crash after the passages were written but before the index was updated.
    chunks = [*semantic.load_chunks(), *CORPUS[2:]]
    vector_store.CHUNKS_FILE.write_text(json.dumps(chunks), encoding="utf-8")
    semantic.reset_caches()
    assert semantic.semantic_query("hydraulic press seals", 1)[0][0]["document"] == "press.pdf"
    assert index_size() == 5


def test_changing_embedding_model_triggers_rebuild(semantic, monkeypatch):
    semantic.add_chunks(CORPUS)
    monkeypatch.setattr(settings, "embedding_model", "another/model")
    before = len(semantic.embed_calls)
    semantic.semantic_query("oil", 1)
    assert len(semantic.embed_calls) == before + 2  # one rebuild of all passages + the query
    assert json.loads(vector_store.META_FILE.read_text())["model"] == "another/model"


def test_failed_embedding_leaves_store_unchanged(semantic, monkeypatch):
    semantic.add_chunks(CORPUS[:2])

    def boom(texts, batch_size=32):
        raise embeddings.EmbeddingError("model offline")

    monkeypatch.setattr(embeddings, "embed_texts", boom)
    with pytest.raises(embeddings.EmbeddingError):
        semantic.add_chunks(CORPUS[2:])
    monkeypatch.setattr(embeddings, "embed_texts", fake_embed)
    assert len(semantic.load_chunks()) == 2 and index_size() == 2


def test_rebuild_index_reembeds_everything(semantic):
    semantic.add_chunks(CORPUS)
    assert semantic.rebuild_index() == 5
    assert semantic.stats()["indexed_vectors"] == 5


def test_hybrid_search_combines_both_signals(semantic):
    semantic.add_chunks(CORPUS)
    results, mode = search.search("oil separator element hours", k=3)
    assert mode == "hybrid"
    assert results[0]["document"] == "compressor.pdf" and 0 < results[0]["score"] <= 1


def test_semantic_only_when_keywords_do_not_match(semantic, monkeypatch):
    semantic.add_chunks(CORPUS)
    monkeypatch.setattr(search, "MIN_SEMANTIC_SCORE", 0.0)
    monkeypatch.setattr(search.KeywordIndex, "search", lambda self, q, k: [])
    results, mode = search.search("servo encoder", k=2)
    assert mode == "semantic" and results


def test_semantic_failure_falls_back_to_keyword(semantic, monkeypatch):
    semantic.add_chunks(CORPUS)

    def broken(query, k):
        raise embeddings.EmbeddingError("model offline")

    monkeypatch.setattr(vector_store, "semantic_query", broken)
    results, mode = search.search("oil separator hours", k=2)
    assert mode == "keyword" and results[0]["document"] == "compressor.pdf"