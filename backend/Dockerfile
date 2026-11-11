# syntax=docker/dockerfile:1.7
#
# ForgeMind AI backend (FastAPI).
#
# Build from the PROJECT ROOT (the app imports `backend.app...` and reads sample data from data/):
#   docker build -f backend/Dockerfile -t forgemind-backend .
#
# Optional semantic search (adds ~2 GB: CPU PyTorch + sentence-transformers + FAISS):
#   docker build -f backend/Dockerfile --build-arg INSTALL_SEMANTIC=true -t forgemind-backend .
#   ...then run with ENABLE_SEMANTIC_SEARCH=true

ARG PYTHON_VERSION=3.12

# ------------------------------------------------------------------------------
# Stage 1: install dependencies into a virtualenv (kept out of the final layer history)
# ------------------------------------------------------------------------------
FROM python:${PYTHON_VERSION}-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:${PATH}"

WORKDIR /build
COPY backend/requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt

ARG INSTALL_SEMANTIC=false
RUN --mount=type=cache,target=/root/.cache/pip \
    if [ "${INSTALL_SEMANTIC}" = "true" ]; then \
        pip install torch --index-url https://download.pytorch.org/whl/cpu \
        && pip install sentence-transformers faiss-cpu; \
    fi

# ------------------------------------------------------------------------------
# Stage 2: slim runtime image, non-root
# ------------------------------------------------------------------------------
FROM python:${PYTHON_VERSION}-slim AS runtime

ARG APP_UID=10001
LABEL org.opencontainers.image.title="ForgeMind AI backend" \
      org.opencontainers.image.description="Industrial Intelligence Copilot: RAG over manuals, SOPs and maintenance records" \
      org.opencontainers.image.source="https://github.com/your-org/forgemind-ai"

ENV PATH="/opt/venv/bin:${PATH}" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_ENV=production \
    # Sample data lives outside /app/data so a volume mounted there cannot hide it.
    SAMPLE_DIR=/app/seed \
    # Model downloads (semantic search) go to the writable data volume.
    HF_HOME=/app/data/.cache/huggingface

# Unprivileged user; /app/data is the only place the app writes (database, uploads, indexes).
RUN groupadd --gid "${APP_UID}" app \
    && useradd --uid "${APP_UID}" --gid app --no-create-home --shell /usr/sbin/nologin app \
    && mkdir -p /app/data/uploads /app/data/processed /app/data/indexes \
    && chown -R app:app /app

WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
COPY --chown=app:app backend/ ./backend/
COPY --chown=app:app data/sample/ ./seed/

USER app
EXPOSE 8000

# `python` is used instead of curl so the image needs no extra packages.
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD ["python", "-c", "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health/live', timeout=3).status == 200 else 1)"]

# One worker on purpose: the passage store and FAISS index are file-backed and guarded by an
# in-process lock. Scale out with a real vector database before adding workers or replicas.
# Behind a reverse proxy, set FORWARDED_ALLOW_IPS to the proxy's address.
CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--proxy-headers"]