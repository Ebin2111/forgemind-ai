"""Split page text into overlapping passages for retrieval.

Strategy (structure-aware, never cuts inside a word unless a single token exceeds the limit):
  1. Break text into units: lines (list items, short sentences) grouped by paragraph.
  2. Break any unit longer than ``chunk_size`` into sentences, then words.
  3. Greedily pack units into chunks of at most ``chunk_size`` characters.
  4. Start each new chunk with the trailing whole units of the previous one (up to ``overlap``
     characters) so an answer spanning a boundary is still retrievable.
"""
import re

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9(\"'\[])")

Unit = tuple[str, str]  # (separator placed before this unit, text)


def _length(units: list[Unit]) -> int:
    """Rendered length of units (the first unit's separator is not rendered)."""
    return sum(len(t) for _, t in units) + sum(len(s) for s, _ in units[1:])


def _render(units: list[Unit]) -> str:
    return "".join((s if i else "") + t for i, (s, t) in enumerate(units))


def _split_oversized(text: str, size: int) -> list[str]:
    """Split text longer than ``size`` into sentences, then words, then raw slices."""
    pieces: list[str] = []
    for sentence in _SENTENCE_SPLIT.split(text):
        if len(sentence) <= size:
            pieces.append(sentence)
            continue
        current = ""
        for word in sentence.split(" "):
            while len(word) > size:  # a single token (e.g. a long URL) larger than the limit
                if current:
                    pieces.append(current)
                    current = ""
                pieces.append(word[:size])
                word = word[size:]
            if current and len(current) + 1 + len(word) > size:
                pieces.append(current)
                current = word
            else:
                current = f"{current} {word}" if current else word
        if current:
            pieces.append(current)
    return pieces


def _to_units(text: str, size: int) -> list[Unit]:
    units: list[Unit] = []
    for p_index, paragraph in enumerate(re.split(r"\n\s*\n", text)):
        lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in paragraph.split("\n")]
        for l_index, line in enumerate(ln for ln in lines if ln):
            lead = "" if not units else ("\n\n" if l_index == 0 and p_index else "\n")
            if len(line) <= size:
                units.append((lead, line))
                continue
            for s_index, piece in enumerate(_split_oversized(line, size)):
                units.append((lead if s_index == 0 else " ", piece))
    return units


def _overlap_tail(units: list[Unit], overlap: int) -> list[Unit]:
    tail: list[Unit] = []
    for unit in reversed(units):
        if overlap <= 0 or _length([unit, *tail]) > overlap:
            break
        tail.insert(0, unit)
    return tail


def chunk_text(text: str, chunk_size: int = 800, overlap: int = 120) -> list[str]:
    """Split text into overlapping chunks of at most ``chunk_size`` characters."""
    if chunk_size < 1:
        raise ValueError("chunk_size must be positive")
    if not 0 <= overlap < chunk_size:
        raise ValueError("overlap must be >= 0 and smaller than chunk_size")

    text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        return []

    chunks: list[str] = []
    current: list[Unit] = []
    for sep, piece in _to_units(text, chunk_size):
        if current and _length(current) + len(sep) + len(piece) > chunk_size:
            chunks.append(_render(current))
            current = _overlap_tail(current, overlap)
            # Drop overlap units until the incoming unit fits alongside them.
            while current and _length(current) + len(sep) + len(piece) > chunk_size:
                current.pop(0)
        current.append((sep, piece))
    if current:
        chunks.append(_render(current))
    return chunks


def chunk_pages(pages: list[dict], document: str, chunk_size: int = 800, overlap: int = 120) -> list[dict]:
    """Chunk page-level text, keeping document name and page number for citations.

    Returns [{"document", "page", "chunk_index", "text"}, ...]; ``chunk_index`` counts within a page.
    """
    out: list[dict] = []
    for page in pages:
        for index, piece in enumerate(chunk_text(page["text"], chunk_size, overlap)):
            out.append({"document": document, "page": page["page"], "chunk_index": index, "text": piece})
    return out