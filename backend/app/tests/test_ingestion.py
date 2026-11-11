import pytest

from backend.app.ingestion.chunker import chunk_pages, chunk_text
from backend.app.ingestion.pdf_loader import PdfLoadError, clean_text, load_pdf, reflow, strip_repeated_lines


# --- chunker --------------------------------------------------------------
@pytest.mark.parametrize("size,overlap", [(100, 0), (200, 40), (300, 50), (800, 120)])
def test_chunks_never_exceed_size_and_cover_all_words(size, overlap):
    text = "\n\n".join(
        f"Section {i}. Isolate the supply, verify zero energy, then remove guard {i}. "
        "Record the reading in the log; notify the supervisor before restart."
        for i in range(30)
    )
    chunks = chunk_text(text, size, overlap)
    assert chunks and all(len(c) <= size for c in chunks)
    covered = " ".join(chunks)
    assert all(word in covered for word in text.split())


def test_overlap_repeats_trailing_text():
    lines = "\n".join(f"Step {i}: tighten bolt number {i} to spec." for i in range(40))
    chunks = chunk_text(lines, 200, 80)
    assert len(chunks) > 2
    last_line_of_first = chunks[0].split("\n")[-1]
    assert last_line_of_first in chunks[1]


def test_no_overlap_means_no_repeated_lines():
    lines = "\n".join(f"Step {i}: tighten bolt number {i}." for i in range(40))
    chunks = chunk_text(lines, 200, 0)
    seen = [ln for c in chunks for ln in c.split("\n")]
    assert len(seen) == len(set(seen))


def test_long_token_is_split_without_exceeding_size():
    chunks = chunk_text("x" * 1000, 300, 50)
    assert all(len(c) <= 300 for c in chunks) and "".join(chunks).count("x") >= 1000


def test_original_behaviour_preserved():
    chunks = chunk_text("Sentence number one. " * 200, chunk_size=300, overlap=50)
    assert len(chunks) > 1 and all(len(c) <= 300 for c in chunks)


def test_chunker_edge_cases():
    assert chunk_text("   \n\n ") == []
    assert chunk_text("short text", 800, 120) == ["short text"]
    with pytest.raises(ValueError):
        chunk_text("abc", 100, 100)
    with pytest.raises(ValueError):
        chunk_text("abc", 0, 0)


def test_chunk_pages_keeps_citation_metadata():
    pages = [{"page": 3, "text": "Replace the filter. " * 60}, {"page": 7, "text": "Short page."}]
    out = chunk_pages(pages, "manual.pdf", 200, 30)
    assert {c["page"] for c in out} == {3, 7}
    assert all(c["document"] == "manual.pdf" for c in out)
    assert [c["chunk_index"] for c in out if c["page"] == 7] == [0]


# --- pdf_loader helpers ---------------------------------------------------
def test_clean_text_fixes_ligatures_hyphenation_and_control_chars():
    raw = "Lock-\nout ﬁlter\x00 pro\xadcedure now"
    assert clean_text(raw) == "Lockout filter procedure now"


def test_reflow_joins_wrapped_lines_but_keeps_list_items():
    raw = "Remove the cover and inspect\nthe seal for wear.\n1. Isolate power\n2. Drain oil\n\nNew paragraph here."
    assert reflow(raw) == "Remove the cover and inspect the seal for wear.\n1. Isolate power\n2. Drain oil\n\nNew paragraph here."


def test_repeated_headers_and_page_numbers_removed():
    pages = [
        {"page": i, "text": f"ACME Service Manual\nBody text for page {i} about seals.\nPage {i} of 6"} for i in range(1, 7)
    ]
    out = strip_repeated_lines(pages)
    assert all(p["text"] == f"Body text for page {p['page']} about seals." for p in out)


def test_boilerplate_kept_when_document_is_short():
    pages = [{"page": i, "text": f"Header\nbody {i}"} for i in range(1, 3)]
    assert strip_repeated_lines(pages) == pages


# --- pdf_loader on real PDFs ---------------------------------------------
reportlab = pytest.importorskip("reportlab")


def _make_pdf(path, pages):
    from reportlab.pdfgen import canvas

    c = canvas.Canvas(str(path))
    for lines in pages:
        for i, line in enumerate(lines):
            c.drawString(72, 750 - 20 * i, line)
        c.showPage()
    c.save()


def test_load_pdf_returns_pages_with_numbers(tmp_path):
    pdf = tmp_path / "m.pdf"
    _make_pdf(pdf, [["Replace the oil separator every 4000 hours."], [], ["Check belt tension monthly."]])
    pages = load_pdf(pdf)
    assert [p["page"] for p in pages] == [1, 3]  # blank page 2 is skipped, numbering preserved
    assert "oil separator" in pages[0]["text"]


def test_load_pdf_rejects_garbage_and_page_limit(tmp_path):
    bad = tmp_path / "bad.pdf"
    bad.write_bytes(b"%PDF-1.4 this is not a real pdf")
    with pytest.raises(PdfLoadError):
        load_pdf(bad)

    pdf = tmp_path / "many.pdf"
    _make_pdf(pdf, [["page"]] * 3)
    with pytest.raises(PdfLoadError, match="limit"):
        load_pdf(pdf, max_pages=2)


def test_numbered_body_lines_on_short_pages_are_not_treated_as_boilerplate():
    pages = [{"page": i, "text": f"Step {i} isolate\nStep {i} drain\nStep {i} refill"} for i in range(1, 7)]
    assert strip_repeated_lines(pages) == pages