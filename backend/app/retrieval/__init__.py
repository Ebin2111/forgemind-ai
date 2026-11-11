"""Finds the passages that answer a question.

* ``embeddings``   - optional sentence-transformers model that turns text into vectors.
* ``vector_store`` - stores passages on disk and keeps the FAISS vector index in step with them.
* ``search``       - keyword (BM25), semantic and hybrid ranking; falls back to keyword when vectors are off.
"""