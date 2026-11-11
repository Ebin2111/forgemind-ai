"""FastAPI application factory.

Run from the project root:
    uvicorn backend.app.main:app --reload --port 8000
"""
import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import __title__, __version__
from .api import api_router
from .core.config import settings
from .core.logging import configure_logging, request_id_ctx
from .core.security import ensure_first_admin
from .db import init_db, session_scope
from .models.db_models import User
from .schemas import ErrorBody, ErrorResponse
from .services.seed import seed_sample_data

logger = logging.getLogger("forgemind")

REQUEST_ID_HEADER = "X-Request-ID"

_STATUS_CODES = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    413: "payload_too_large",
    422: "validation_error",
    429: "rate_limited",
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging(settings.log_level, settings.log_format)
    logger.info("Starting %s v%s (%s)", __title__, __version__, settings.app_env)
    init_db()
    if not settings.auth_enabled:
        logger.warning("AUTH_ENABLED=false: the API is open to anyone who can reach it")
    else:
        with session_scope() as db:
            if ensure_first_admin(db):
                logger.info("Created the first administrator account: %s", settings.admin_email.strip().lower())
            elif not db.scalar(select(func.count()).select_from(User)):
                logger.warning(
                    "There are no user accounts and ADMIN_EMAIL / ADMIN_PASSWORD (8+ characters) are not set, "
                    "so nobody can sign in. Set them in .env (see .env.example)."
                )
    if settings.seed_sample_data:
        with session_scope() as db:
            if seed_sample_data(db):
                logger.info("Seeded sample equipment and work orders")
    else:
        logger.info("Sample data seeding is off (SEED_SAMPLE_DATA=false)")
    logger.info("Configuration: %s", settings.safe_summary())
    if not settings.gemini_enabled:
        logger.warning("GEMINI_API_KEY is not set; answers will fall back to extractive excerpts")
    yield
    logger.info("Shutting down")


def _error_response(status_code: int, message: str, code: str | None = None, details: list | None = None,
                    headers: dict[str, str] | None = None) -> JSONResponse:
    body = ErrorResponse(
        error=ErrorBody(
            code=code or _STATUS_CODES.get(status_code, "error"),
            message=message,
            request_id=request_id_ctx.get(),
            details=details,
        )
    )
    return JSONResponse(status_code=status_code, content=body.model_dump(exclude_none=True), headers=headers)


def _register_middleware(app: FastAPI) -> None:
    app.add_middleware(GZipMiddleware, minimum_size=1024)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,  # session cookie for the login page; origins are an explicit list, never "*"
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["*"],
        expose_headers=[REQUEST_ID_HEADER, "X-Total-Count"],
    )

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        # Reuse a caller-supplied ID (e.g. from a gateway) or mint one.
        rid = request.headers.get(REQUEST_ID_HEADER) or uuid.uuid4().hex[:12]
        token = request_id_ctx.set(rid)
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            logger.exception("Unhandled error: %s %s", request.method, request.url.path)
            response = _error_response(500, "Internal server error.", "internal_error")
        elapsed_ms = (time.perf_counter() - started) * 1000
        response.headers[REQUEST_ID_HEADER] = rid
        logger.info("%s %s -> %d (%.0f ms)", request.method, request.url.path, response.status_code, elapsed_ms)
        request_id_ctx.reset(token)
        return response


def _register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(StarletteHTTPException)
    async def http_error(_: Request, exc: StarletteHTTPException):
        return _error_response(exc.status_code, str(exc.detail), headers=getattr(exc, "headers", None))

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError):
        details = [
            # loc is (where, name, ...) e.g. ("query", "status"); report just the field path
            {"field": ".".join(str(p) for p in e["loc"][1:]) or str(e["loc"][0]), "message": e["msg"]}
            for e in exc.errors()
        ]
        return _error_response(422, "Request validation failed.", details=details)

    @app.exception_handler(Exception)
    async def unhandled_error(_: Request, exc: Exception):
        logger.exception("Unhandled error")
        return _error_response(500, "Internal server error.", "internal_error")


def create_app() -> FastAPI:
    app = FastAPI(
        title=__title__,
        description="Industrial Intelligence Copilot: retrieval-augmented answers over manuals, SOPs and maintenance records.",
        version=__version__,
        lifespan=lifespan,
        # Hide interactive docs in production unless you front them with auth.
        docs_url=None if settings.is_production else "/docs",
        redoc_url=None if settings.is_production else "/redoc",
        openapi_url=None if settings.is_production else "/openapi.json",
    )
    _register_middleware(app)
    _register_error_handlers(app)

    app.include_router(api_router, prefix=settings.api_prefix)
    return app


app = create_app()