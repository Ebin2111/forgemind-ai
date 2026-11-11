"""Question answering over indexed documents (retrieve -> generate -> cite)."""
import logging
import time

from fastapi import APIRouter

from ..core.config import settings
from ..generation.gemini_client import generate_answer
from ..retrieval import search as retrieval
from ..schemas import AskRequest, AskResponse, Source
from ..services.smalltalk import reply as small_talk

logger = logging.getLogger(__name__)
router = APIRouter(tags=["assistant"])


@router.post("/ask", response_model=AskResponse, summary="Ask a question; get an answer with sources")
def ask(req: AskRequest) -> AskResponse:
    started = time.perf_counter()
    greeting = small_talk(req.question)
    if greeting:  # "hi", "thanks", "who are you": answered directly, no document search
        return AskResponse(answer=greeting, sources=[], retrieval_mode="keyword", generated_by="assistant", latency_ms=0)
    passages, mode = retrieval.search(req.question, req.top_k or settings.top_k)
    result = generate_answer(req.question, passages)
    latency_ms = int((time.perf_counter() - started) * 1000)

    logger.info(
        "ask: retrieval=%s passages=%d generated_by=%s cited=%s fallback=%s latency_ms=%d",
        mode, len(passages), result.generated_by, list(result.cited), result.fallback_reason, latency_ms,
    )
    return AskResponse(
        answer=result.answer,
        sources=[
            Source(document=p["document"], page=p["page"], excerpt=p["text"][:500], score=p["score"])
            for p in passages
        ],
        retrieval_mode=mode,
        generated_by=result.generated_by,
        latency_ms=latency_ms,
    )