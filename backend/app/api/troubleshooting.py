"""Fault diagnosis: symptom (+ equipment and fault code) -> likely causes and fixes, with sources."""
import logging
import time

from fastapi import APIRouter, HTTPException, status

from ..core.config import settings
from ..db import DbSession
from ..generation.gemini_client import generate_answer
from ..retrieval import search as retrieval
from ..schemas import ErrorResponse, Source, TroubleshootRequest, TroubleshootResponse
from ..services import troubleshooting as service

logger = logging.getLogger(__name__)
router = APIRouter(tags=["troubleshooting"])


@router.post(
    "/troubleshoot",
    response_model=TroubleshootResponse,
    summary="Diagnose a fault; get causes, checks and fixes with sources",
    responses={status.HTTP_404_NOT_FOUND: {"model": ErrorResponse, "description": "Unknown equipment tag"}},
)
def troubleshoot(req: TroubleshootRequest, db: DbSession) -> TroubleshootResponse:
    started = time.perf_counter()

    equipment = None
    if req.equipment_tag:
        equipment = service.find_equipment(db, req.equipment_tag)
        if equipment is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"Equipment '{req.equipment_tag}' not found.")

    ctx = service.gather_context(db, req, equipment)
    passages, mode = retrieval.search(service.build_search_query(req, equipment), req.top_k or settings.top_k)
    result = generate_answer(service.build_question(req, ctx), passages)
    latency_ms = int((time.perf_counter() - started) * 1000)

    logger.info(
        "troubleshoot: equipment=%s fault_code=%s related=%d retrieval=%s passages=%d generated_by=%s "
        "fallback=%s latency_ms=%d",
        equipment.tag if equipment else None, req.fault_code, len(ctx.related), mode, len(passages),
        result.generated_by, result.fallback_reason, latency_ms,
    )
    return TroubleshootResponse(
        answer=result.answer,
        equipment=equipment,
        history=ctx.history,
        related_work_orders=ctx.related,
        sources=[
            Source(document=p["document"], page=p["page"], excerpt=p["text"][:500], score=p["score"])
            for p in passages
        ],
        retrieval_mode=mode,
        generated_by=result.generated_by,
        latency_ms=latency_ms,
    )