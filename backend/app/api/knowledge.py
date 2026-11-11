"""Knowledge base: browse and search the indexed passages behind every answer."""
from typing import Optional

from fastapi import APIRouter, Query, Response
from sqlalchemy import func, select

from ..db import DbSession
from ..models.db_models import Document
from ..retrieval import search as retrieval
from ..retrieval import vector_store
from ..schemas import KnowledgeStats, PassageOut

router = APIRouter(prefix="/knowledge", tags=["knowledge base"])


@router.get("/stats", response_model=KnowledgeStats, summary="Size of the indexed knowledge base")
def stats(db: DbSession) -> KnowledgeStats:
    totals = db.execute(select(func.count(), func.coalesce(func.sum(Document.pages), 0))).one()
    info = vector_store.stats()
    return KnowledgeStats(
        documents=totals[0],
        pages=int(totals[1]),
        passages=info["passages"],
        indexed_vectors=info["indexed_vectors"],
        semantic_enabled=info["semantic_enabled"],
        embedding_model=info["embedding_model"],
    )


@router.get("/passages", response_model=list[PassageOut], summary="Browse or search indexed passages")
def passages(
    response: Response,
    document: Optional[str] = Query(None, description="Only passages from this file name"),
    q: Optional[str] = Query(None, max_length=200, description="Keyword search; results are ranked by relevance"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> list[PassageOut]:
    chunks = vector_store.load_chunks()
    if document:
        chunks = [c for c in chunks if c["document"] == document]

    if q and q.strip():
        ranked = retrieval.keyword_search(q, chunks, len(chunks))
    else:
        ranked = [{**c, "score": None} for c in chunks]

    response.headers["X-Total-Count"] = str(len(ranked))
    return [
        PassageOut(
            document=c["document"],
            page=c["page"],
            chunk_index=c.get("chunk_index", 0),
            text=c["text"],
            score=c["score"],
        )
        for c in ranked[offset : offset + limit]
    ]