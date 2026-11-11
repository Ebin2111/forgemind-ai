"""PDF text extraction.

Pipeline: extract per page -> clean (unicode, hyphenation, control chars) -> drop repeated
headers/footers -> reflow hard-wrapped lines into sentences, keeping list items and paragraphs.

Returns one ``{"page": n, "text": ...}`` entry per page that contains text, so citations can
point at real page numbers. Scanned (image-only) PDFs yield no pages; they need OCR first.
"""
import logging
import re
import unicodedata
from collections import Counter
from pathlib import Path
from typing import TypedDict

from pypdf import PdfReader

logger = logging.getLogger(__name__)

MAX_PAGES = 2000

_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_HYPHEN_BREAK = re.compile(r"([a-z])-\n([a-z])")
_LIST_ITEM = re.compile(r"^\s*(?:[-•*▪●◦‣–]\s|\d{1,3}[.)]\s|\(?[a-zA-Z][.)]\s|step\s+\d+\b)", re.IGNORECASE)
_SENTENCE_END = re.compile(r"[.!?:;]\s*$")


class Page(TypedDict):
    page: int
    text: str


class PdfLoadError(Exception):
    """The PDF could not be read (corrupt, password-protected or too large). Message is user-safe."""


def clean_text(raw: str) -> str:
    """Normalise extracted text but keep line breaks (they are used later for reflow)."""
    text = unicodedata.normalize("NFKC", raw)  # ligatures (fi), non-breaking spaces, full-width forms
    text = text.replace("\xad", "").replace("\r\n", "\n").replace("\r", "\n")  # soft hyphen, newlines
    text = _CONTROL_CHARS.sub("", text)
    text = re.sub(r"[ \t]+", " ", text)
    return _HYPHEN_BREAK.sub(r"\1\2", text)  # "lock-\nout" -> "lockout"


_PAGE_NUMBER_ONLY = re.compile(r"^[-–—\s]*\d+[-–—\s]*$")  # "12", "- 12 -"
_PAGE_N_OF_M = re.compile(r"\bpage\s*\d+(?:\s*(?:of|/)\s*\d+)?", re.IGNORECASE)  # "Page 3 of 40"


def _boilerplate_key(line: str) -> str:
    """Comparison key for repeated-line detection.

    Only genuine page-number patterns are digit-masked ('Page 3 of 40' == 'Page 4 of 40').
    Everything else must match exactly, so numbered body text ('Step 3 ...') is never treated
    as a running header or footer.
    """
    line = re.sub(r"\s+", " ", line.strip().lower())
    if _PAGE_NUMBER_ONLY.match(line):
        return "#"
    return _PAGE_N_OF_M.sub("page #", line)


def strip_repeated_lines(pages: list[Page], *, min_pages: int = 4, threshold: float = 0.5) -> list[Page]:
    """Remove running headers/footers: short lines in the top/bottom two lines of most pages."""
    if len(pages) < min_pages:
        return pages

    def zone(lines: list[str]) -> set[int]:
        # Top/bottom two lines, but never more than a third of the page each, so body text
        # on short pages is never mistaken for a header or footer.
        n, k = len(lines), min(2, len(lines) // 3)
        return set(range(k)) | set(range(n - k, n))

    def is_candidate(line: str) -> bool:
        return len(line) <= 120 and len(line.split()) <= 8  # headers/footers are short

    counts: Counter[str] = Counter()
    for p in pages:
        lines = [ln.strip() for ln in p["text"].split("\n") if ln.strip()]
        keys = {_boilerplate_key(lines[i]) for i in zone(lines) if is_candidate(lines[i])}
        counts.update(keys)

    repeated = {k for k, c in counts.items() if c / len(pages) >= threshold}
    if not repeated:
        return pages

    out: list[Page] = []
    for p in pages:
        lines = [ln.strip() for ln in p["text"].split("\n") if ln.strip()]
        drop = {i for i in zone(lines) if is_candidate(lines[i]) and _boilerplate_key(lines[i]) in repeated}
        out.append({"page": p["page"], "text": "\n".join(ln for i, ln in enumerate(lines) if i not in drop)})
    logger.debug("Removed %d repeated header/footer patterns", len(repeated))
    return out


def reflow(text: str) -> str:
    """Join hard-wrapped lines into sentences; keep list items and paragraph breaks on their own lines."""
    paragraphs: list[str] = []
    for block in re.split(r"\n\s*\n", text):
        lines = [ln.strip() for ln in block.split("\n") if ln.strip()]
        if not lines:
            continue
        rows, buf = [], lines[0]
        for line in lines[1:]:
            if _LIST_ITEM.match(line) or (_SENTENCE_END.search(buf) and line[:1].isupper()):
                rows.append(buf)
                buf = line
            else:
                buf = f"{buf} {line}"
        rows.append(buf)
        paragraphs.append("\n".join(rows))
    return "\n\n".join(paragraphs)


def load_pdf(path: Path | str, *, max_pages: int = MAX_PAGES, strip_boilerplate: bool = True) -> list[Page]:
    """Extract text from a PDF. Returns [{"page": 1, "text": "..."}, ...] for pages with text.

    Raises PdfLoadError for unreadable, encrypted or oversized files. A page that fails to
    extract is skipped (and logged) rather than failing the whole document.
    """
    path = Path(path)
    try:
        reader = PdfReader(str(path), strict=False)
    except Exception as exc:
        raise PdfLoadError("The file is not a readable PDF.") from exc

    if reader.is_encrypted:
        try:
            unlocked = reader.decrypt("")  # many PDFs are 'encrypted' with an empty user password
        except Exception:
            unlocked = 0
        if not unlocked:
            raise PdfLoadError("The PDF is password-protected.")

    total = len(reader.pages)
    if total > max_pages:
        raise PdfLoadError(f"The PDF has {total} pages; the limit is {max_pages}.")

    pages: list[Page] = []
    failed: list[int] = []
    for number, page in enumerate(reader.pages, start=1):
        try:
            raw = page.extract_text() or ""
        except Exception:
            logger.warning("Text extraction failed on page %d of %s", number, path.name, exc_info=True)
            failed.append(number)
            continue
        text = clean_text(raw).strip()
        if text:
            pages.append({"page": number, "text": text})

    if strip_boilerplate:
        pages = strip_repeated_lines(pages)

    result: list[Page] = []
    for p in pages:
        text = reflow(p["text"])
        if text:
            result.append({"page": p["page"], "text": text})

    if failed:
        logger.warning("%s: skipped %d unreadable page(s): %s", path.name, len(failed), failed[:10])
    logger.info("Loaded %s: %d/%d pages with text", path.name, len(result), total)
    return result