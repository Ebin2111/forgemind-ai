"""Document upload, listing and deletion."""
import logging
import re
import time
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select

from ..core.config import settings
from ..core.security import require_admin
from ..db import DbSession
from ..generation.gemini_client import generate_answer
from ..ingestion.chunker import chunk_pages
from ..ingestion.pdf_loader import PdfLoadError, load_pdf
from ..models.db_models import Document
from ..retrieval import vector_store
from ..services.equipment_naming import register_from_document
from ..schemas import DeleteOut, DocumentOut, DocumentSummary, DocumentUploaded

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/documents", tags=["documents"])

_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]")
SUMMARY_PASSAGES = 8  # passages sampled across the document for a summary
SUMMARY_QUESTION = (
    "Summarize the document '{name}': what it is for, the equipment it covers, and its key procedures, "
    "intervals, limits and warnings."
)


def _safe_filename(raw: str) -> str:
    name = _SAFE_NAME.sub("_", Path(raw).name).lstrip(".") or "document.pdf"
    return name[:200]


def _read_limited(upload: UploadFile) -> bytes:
    """Read the upload but refuse anything over the size limit without buffering it all."""
    limit = settings.max_upload_bytes
    data = upload.file.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(413, f"File exceeds {settings.max_upload_mb} MB limit.")
    return data


@router.get("", response_model=list[DocumentOut], summary="List indexed documents")
def list_documents(db: DbSession):
    return db.scalars(select(Document).order_by(Document.uploaded_at.desc())).all()


@router.post(
    "/upload", response_model=DocumentUploaded, status_code=status.HTTP_201_CREATED, summary="Upload and index a PDF",
    dependencies=[Depends(require_admin)],
)
def upload_document(db: DbSession, file: UploadFile = File(...)):
    # Plain `def` so the CPU-bound parsing runs in FastAPI's threadpool, not the event loop.
    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Only PDF files are supported.")

    content = _read_limited(file)
    if not content.startswith(b"%PDF-"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "File is not a valid PDF.")

    name = _safe_filename(file.filename)
    dest = settings.uploads_dir / name
    tmp = settings.uploads_dir / f".{uuid.uuid4().hex}.tmp"
    tmp.write_bytes(content)

    try:
        pages = load_pdf(tmp)
    except PdfLoadError as exc:
        tmp.unlink(missing_ok=True)
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    except Exception:
        tmp.unlink(missing_ok=True)
        logger.warning("Could not parse uploaded PDF %s", name, exc_info=True)
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Could not read this PDF.")
    if not pages:
        tmp.unlink(missing_ok=True)
        raise HTTPException(422, "No extractable text found (scanned PDFs need OCR).")

    tmp.replace(dest)  # atomic: only a fully validated file lands in uploads/

    existing = db.scalar(select(Document).where(Document.filename == name))
    if existing:  # re-upload replaces the previous version
        vector_store.remove_document(name)
        db.delete(existing)
        db.flush()

    chunks = chunk_pages(pages, name, settings.chunk_size, settings.chunk_overlap)
    try:
        vector_store.add_chunks(chunks)
        doc = Document(filename=name, pages=len(pages), chunks=len(chunks))
        db.add(doc)
        machine = register_from_document(db, name) if settings.auto_register_equipment else None
        db.commit()
    except Exception:
        db.rollback()
        vector_store.remove_document(name)
        logger.exception("Indexing failed for %s", name)
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Indexing failed.")

    db.refresh(doc)
    logger.info("Indexed %s: %d pages, %d chunks%s", name, len(pages), len(chunks),
                f"; registered equipment {machine.tag}" if machine else "")
    return DocumentUploaded.model_validate({**DocumentOut.model_validate(doc).model_dump(), "registered_equipment": machine})


@router.delete("/{doc_id}", response_model=DeleteOut, summary="Delete a document and its index entries", dependencies=[Depends(require_admin)])
def delete_document(doc_id: int, db: DbSession):
    doc = db.get(Document, doc_id)
    if not doc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found.")
    vector_store.remove_document(doc.filename)
    (settings.uploads_dir / doc.filename).unlink(missing_ok=True)
    db.delete(doc)
    db.commit()
    return DeleteOut(deleted=doc.filename)


def _stored_pdf(doc: Document) -> Path:
    """Path of the uploaded file for ``doc``; 404 if it is missing from disk."""
    root = settings.uploads_dir.resolve()
    path = (root / doc.filename).resolve()
    if path.parent != root or not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "The stored file is missing. Upload the document again.")
    return path


def _get_document(db, doc_id: int) -> Document:
    doc = db.get(Document, doc_id)
    if not doc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found.")
    return doc


def _spread(items: list, n: int) -> list:
    """At most ``n`` items spread evenly from first to last, so a summary covers the whole document."""
    if len(items) <= n:
        return list(items)
    return [items[round(i * (len(items) - 1) / (n - 1))] for i in range(n)]


@router.get("/{doc_id}/download", summary="Download the original PDF")
def download_document(doc_id: int, db: DbSession):
    doc = _get_document(db, doc_id)
    return FileResponse(_stored_pdf(doc), media_type="application/pdf", filename=doc.filename)


@router.post(
    "/{doc_id}/reindex", response_model=DocumentOut, summary="Read the stored PDF again and rebuild its index",
    dependencies=[Depends(require_admin)],
)
def reindex_document(doc_id: int, db: DbSession):
    doc = _get_document(db, doc_id)
    path = _stored_pdf(doc)
    try:
        pages = load_pdf(path)
    except PdfLoadError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    except Exception:
        logger.warning("Could not parse stored PDF %s", doc.filename, exc_info=True)
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Could not read this PDF.")
    if not pages:
        raise HTTPException(422, "No extractable text found (scanned PDFs need OCR).")

    chunks = chunk_pages(pages, doc.filename, settings.chunk_size, settings.chunk_overlap)
    try:
        vector_store.remove_document(doc.filename)
        vector_store.add_chunks(chunks)
        doc.pages, doc.chunks = len(pages), len(chunks)
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Re-indexing failed for %s", doc.filename)
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Re-indexing failed. Please try again.")
    db.refresh(doc)
    logger.info("Re-indexed %s: %d pages, %d chunks", doc.filename, len(pages), len(chunks))
    return doc


@router.post("/{doc_id}/summary", response_model=DocumentSummary, summary="AI summary of one document")
def summarize_document(doc_id: int, db: DbSession):
    started = time.perf_counter()
    doc = _get_document(db, doc_id)
    chunks = [c for c in vector_store.load_chunks() if c["document"] == doc.filename]
    if not chunks:
        raise HTTPException(422, "This document has no indexed text. Try re-indexing it.")
    passages = [{**c, "score": 0.0} for c in _spread(chunks, SUMMARY_PASSAGES)]
    result = generate_answer(SUMMARY_QUESTION.format(name=doc.filename), passages)
    return DocumentSummary(
        answer=result.answer,
        generated_by=result.generated_by,
        passages_used=len(passages),
        latency_ms=int((time.perf_counter() - started) * 1000),
    )