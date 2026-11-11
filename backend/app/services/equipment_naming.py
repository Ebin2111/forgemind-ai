"""Turn an uploaded manual into a registry entry.

Only the file name is used: nothing is read out of the PDF and guessed. The user can edit every field on the
Equipment page afterwards. Tags are generated (``<INITIALS>-<number>``) and are always unique.
"""
import re

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models.db_models import Equipment

# Words that describe the document, not the machine.
_NOISE = {
    "manual", "manuals", "guide", "handbook", "sop", "pdf", "instruction", "instructions", "operation", "operations",
    "operating", "operator", "user", "users", "service", "servicing", "maintenance", "datasheet", "data", "sheet",
    "installation", "owner", "owners", "repair", "parts", "catalog", "catalogue", "document", "doc", "copy", "final",
}
_VERSION = re.compile(r"^(v|rev|ver)?\d{1,2}(\.\d+)*$", re.IGNORECASE)


def guess_name(filename: str) -> str:
    """'Atlas_Copco-GA30_Operation_Manual (2).pdf' -> 'Atlas Copco GA30'. Empty string if nothing is left."""
    stem = re.sub(r"\.pdf$", "", filename, flags=re.IGNORECASE)
    stem = re.sub(r"\(\d+\)|\[\d+\]", " ", stem)
    words = [w for w in re.split(r"[\s_\-.,]+", stem) if w]
    kept = [w for w in words if w.lower() not in _NOISE and not _VERSION.match(w)]
    name = " ".join(kept).strip()
    return name[:200]


def _initials(name: str) -> str:
    letters = "".join(w[0] for w in re.findall(r"[A-Za-z0-9]+", name))[:3].upper()
    return letters or "EQ"


def next_tag(db: Session, name: str) -> str:
    prefix = _initials(name)
    taken = {t for (t,) in db.execute(select(Equipment.tag).where(Equipment.tag.like(f"{prefix}-%")))}
    number = 1
    while f"{prefix}-{number:03d}" in taken:
        number += 1
    return f"{prefix}-{number:03d}"


def register_from_document(db: Session, filename: str) -> Equipment | None:
    """Add the machine a manual describes. Returns None when the name is empty or the machine already exists."""
    name = guess_name(filename)
    if len(name) < 2:
        return None
    exists = db.scalar(select(Equipment.id).where(func.lower(Equipment.name) == name.lower()))
    if exists:
        return None
    equipment = Equipment(tag=next_tag(db, name), name=name, type="", location="", manufacturer="", status="operational")
    db.add(equipment)
    db.flush()
    return equipment
    