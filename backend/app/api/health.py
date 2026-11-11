"""Health endpoints.

* ``/health/live``  - liveness: the process is up. Use for container restarts.
* ``/health/ready`` - readiness: each dependency is checked; 503 when any is down. Use for load balancers.
* ``/health``       - detailed status for the dashboard and humans.
"""
import logging
import os
import time
from collections.abc import Callable

from fastapi import APIRouter, Response, status

from .. import __version__
from ..core.config import settings
from ..db import check_db, db_status
from ..generation.gemini_client import gemini_configured
from ..retrieval import vector_store
from ..schemas import ComponentCheck, HealthOut, LivenessOut, ReadinessOut

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/health", tags=["system"])

_STARTED_AT = time.monotonic()

CheckResult = bool | tuple[bool, str | None]


def _uptime() -> float:
    return round(time.monotonic() - _STARTED_AT, 1)


def _run_check(name: str, check: Callable[[], CheckResult]) -> ComponentCheck:
    """Run one dependency check, timing it and converting any exception into a failed check."""
    started = time.perf_counter()
    try:
        result = check()
        ok, detail = result if isinstance(result, tuple) else (bool(result), None)
    except Exception as exc:
        logger.warning("Health check '%s' failed", name, exc_info=True)
        ok, detail = False, type(exc).__name__
    return ComponentCheck(
        name=name,
        ok=ok,
        latency_ms=round((time.perf_counter() - started) * 1000, 2),
        detail=detail,
    )


def _check_database() -> CheckResult:
    return db_status()


def _check_storage() -> CheckResult:
    """Data directories exist and are writable (uploads must be accepted, indexes persisted)."""
    dirs = (settings.uploads_dir, settings.processed_dir, settings.indexes_dir)
    broken = [d.name for d in dirs if not (d.is_dir() and os.access(d, os.W_OK))]
    return (False, f"not writable: {', '.join(broken)}") if broken else True


def _check_index() -> CheckResult:
    """The chunk store can be read; reports how many passages are searchable."""
    return True, f"{len(vector_store.load_chunks())} chunks"


@router.get("", response_model=HealthOut, summary="Detailed service status")
def health() -> HealthOut:
    db_ok = check_db()
    return HealthOut(
        status="ok" if db_ok else "degraded",
        version=__version__,
        environment=settings.app_env,
        uptime_seconds=_uptime(),
        database=db_ok,
        semantic_search=vector_store.semantic_enabled(),
        gemini_configured=gemini_configured(),
        indexed_chunks=len(vector_store.load_chunks()),
    )


@router.get("/live", response_model=LivenessOut, summary="Liveness probe")
def live() -> LivenessOut:
    return LivenessOut(status="alive", uptime_seconds=_uptime())


@router.get(
    "/ready",
    response_model=ReadinessOut,
    responses={503: {"model": ReadinessOut, "description": "A dependency is unavailable"}},
    summary="Readiness probe",
)
def ready(response: Response) -> ReadinessOut:
    checks = [
        _run_check("database", _check_database),
        _run_check("storage", _check_storage),
        _run_check("index", _check_index),
    ]
    all_ok = all(c.ok for c in checks)
    if not all_ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return ReadinessOut(status="ready" if all_ok else "not_ready", checks=checks)